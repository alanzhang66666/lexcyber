package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * v1.3 §4.8.3 + ADR-0004/0005 — 模块确认。
 * 「有效确认」= confirmed_version_id != null && stale == false（§5.9 公式，不在此叠加查询）。
 * 默认只允许批准 latest（§4.8.3 锁定规则）。
 */
@Service
public class ModuleConfirmationService {
    private final JdbcTemplate jdbc;

    public ModuleConfirmationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** §5.9 公式。下游判定一律走这里（INV-PIPE-003）。 */
    public boolean isEffectivelyConfirmed(String caseId, String module) {
        List<Boolean> rows = jdbc.query("""
                SELECT confirmed_version_id IS NOT NULL AND NOT stale
                FROM app.module_head WHERE case_id = ?::uuid AND module = ?
                """, (rs, ignored) -> rs.getBoolean(1), caseId, module);
        return !rows.isEmpty() && rows.get(0);
    }

    public void requireEffectiveConfirmation(String caseId, String module) {
        if (!isEffectivelyConfirmed(caseId, module)) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_NOT_CONFIRMED",
                    "模块尚无有效确认（未确认或已失效）");
        }
    }

    /**
     * 批准 stream 的 latest version：§4.8.3 可批准校验 + 防御性依赖校验。
     * 锁序统一为 stream → head（与 §4.8.2 publish 同序）：head→stream 会与
     * publish 的 stream→head 形成互等死锁；head 的 stream 绑定不可变，可先做无锁读。
     */
    @Transactional
    public UUID confirm(String caseId, String module, UUID actorId) {
        List<Map<String, Object>> heads = jdbc.queryForList("""
                SELECT artifact_stream_id, confirmed_version_id
                FROM app.module_head WHERE case_id = ?::uuid AND module = ?
                """, caseId, module);
        if (heads.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "MODULE_NOT_FOUND", "模块 head 不存在");
        }
        UUID streamId = (UUID) heads.get(0).get("artifact_stream_id");

        Map<String, Object> stream = jdbc.queryForMap("""
                SELECT latest_version_id FROM app.artifact_stream
                WHERE artifact_stream_id = ? FOR SHARE
                """, streamId);
        UUID latest = (UUID) stream.get("latest_version_id");

        Map<String, Object> head = jdbc.queryForMap("""
                SELECT confirmed_version_id FROM app.module_head
                WHERE case_id = ?::uuid AND module = ? FOR UPDATE
                """, caseId, module);
        UUID alreadyConfirmed = (UUID) head.get("confirmed_version_id");
        if (latest == null) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_NOT_CONFIRMABLE", "模块尚无工件版本");
        }
        if (latest.equals(alreadyConfirmed)) {
            List<Boolean> fresh = jdbc.query(
                    "SELECT NOT stale FROM app.module_head WHERE case_id = ?::uuid AND module = ?",
                    (rs, ignored) -> rs.getBoolean(1), caseId, module);
            if (!fresh.isEmpty() && fresh.get(0)) {
                throw new ApiException(HttpStatus.CONFLICT, "MODULE_CONFIRMED", "模块已确认");
            }
        }
        // 可批准性：不是 blocked（§4.8.3）
        String outcome = jdbc.queryForObject(
                "SELECT outcome_status FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, latest);
        if ("blocked".equals(outcome)) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_BLOCKED", "blocked 版本不可确认");
        }
        // 防御性校验（ADR-0005 §3）：事实依赖若存在，必须仍指向当前 head；
        // 失败说明 stale 传播漏网 → 审计 + 409，不是正常路径
        Long staleDeps = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.artifact_facts_dependency afd
                JOIN app.facts_head h ON h.case_id = ?::uuid
                WHERE afd.artifact_version_id = ?
                  AND h.confirmed_facts_version_id IS DISTINCT FROM afd.facts_version_id
                """, Long.class, caseId, latest);
        if (staleDeps != null && staleDeps > 0L) {
            jdbc.update("""
                    INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                    VALUES ('system', 'stale_propagation_gap', 'module_head', ?,
                            jsonb_build_object('caseId', ?::text, 'module', ?, 'artifactVersionId', ?::text))
                    """, module + "@" + caseId, caseId, module, latest.toString());
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "依赖快照已失效（stale 传播漏网），已阻断并记录");
        }
        jdbc.update("""
                UPDATE app.module_head
                SET confirmed_version_id = ?, stale = false, stale_reason = NULL, updated_at = now()
                WHERE case_id = ?::uuid AND module = ?
                """, latest, caseId, module);
        return latest;
    }
}
