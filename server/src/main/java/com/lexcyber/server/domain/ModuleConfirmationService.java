package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.EngineRegistryClient;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.beans.factory.annotation.Autowired;
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
    private final EngineRegistryClient registry;

    public ModuleConfirmationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        this.registry = new EngineRegistryClient();
    }

    @Autowired
    public ModuleConfirmationService(JdbcTemplate jdbc, EngineRegistryClient registry) {
        this.jdbc = jdbc;
        this.registry = registry;
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
        requireEffectiveArtifactVersion(caseId, module);
    }

    /**
     * Returns the exact effective version while holding the module stream and
     * head shares.  Downstream execution gates use this method so a publisher
     * cannot replace the upstream version between the gate and task creation.
     */
    public UUID requireEffectiveArtifactVersion(String caseId, String module) {
        registry.lockBarrier(jdbc);
        lockFactsHead(caseId);
        List<UUID> streamIds = jdbc.query("""
                SELECT artifact_stream_id FROM app.module_head
                WHERE case_id = ?::uuid AND module = ?
                """, (rs, ignored) -> rs.getObject(1, UUID.class), caseId, module);
        if (streamIds.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_NOT_CONFIRMED",
                    "模块尚无有效确认（未确认或已失效）");
        }
        UUID streamId = streamIds.get(0);
        // Explicit stream lock before head lock.  This makes the lock order
        // visible and prevents the planner from taking the head first.
        jdbc.queryForObject("""
                SELECT artifact_stream_id FROM app.artifact_stream
                WHERE artifact_stream_id = ? FOR SHARE
                """, UUID.class, streamId);
        Map<String, Object> head = jdbc.queryForMap("""
                SELECT confirmed_version_id, stale FROM app.module_head
                WHERE case_id = ?::uuid AND module = ? FOR SHARE
                """, caseId, module);
        UUID confirmed = (UUID) head.get("confirmed_version_id");
        if (confirmed == null || Boolean.TRUE.equals(head.get("stale"))) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_NOT_CONFIRMED",
                    "模块尚无有效确认（未确认或已失效）");
        }
        registry.requireValid(jdbc, confirmed);
        return confirmed;
    }

    private void lockFactsHead(String caseId) {
        // Legacy demo artifacts may have no facts dependency/head. Lock an
        // existing baseline without turning that compatibility path into 500.
        // v2 dispatch separately requires a confirmed baseline.
        jdbc.queryForList("""
                SELECT case_id FROM app.facts_head
                WHERE case_id = ?::uuid FOR SHARE
                """, caseId);
    }

    /**
     * Sentencing's upstream gate.  The conviction stream is locked before a
     * sentencing stream can be published, preserving the ordered-stream lock
     * rule.  The returned id is the exact frozen dependency to put in task
     * metadata and the engine result.
     */
    public UUID requireEffectiveConviction(String caseId) {
        return requireEffectiveArtifactVersion(caseId, ModulePolicies.CONVICTION);
    }

    /**
     * Defensive confirmation check for a sentencing artifact.  The upstream
     * share locks are held by the surrounding transaction until the head move.
     */
    private void requireSentencingDependency(String caseId, UUID sentencingVersionId,
                                             UUID convictionVersionId) {
        Long dependency = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM app.artifact_artifact_dependency d
                JOIN app.artifact_version upstream
                  ON upstream.artifact_version_id = d.depends_on_artifact_version_id
                JOIN app.artifact_stream s
                  ON s.artifact_stream_id = upstream.artifact_stream_id
                WHERE d.artifact_version_id = ?
                  AND d.depends_on_artifact_version_id = ?
                  AND s.case_id = ?::uuid AND s.kind = 'conviction'
                  AND s.scope_key = 'module:conviction'
                """, Long.class, sentencingVersionId, convictionVersionId, caseId);
        if (dependency == null || dependency != 1L) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "量刑版本未冻结当前有效定罪工件，确认被阻断");
        }
    }

    /**
     * 批准 stream 的 latest version：§4.8.3 可批准校验 + 防御性依赖校验。
     * 锁序统一为 stream → head（与 §4.8.2 publish 同序）：head→stream 会与
     * publish 的 stream→head 形成互等死锁；head 的 stream 绑定不可变，可先做无锁读。
     */
    @Transactional
    public UUID confirm(String caseId, String module, UUID actorId) {
        registry.lockBarrier(jdbc);
        LegalAnalysisContext.lockCase(jdbc, caseId);
        List<Map<String, Object>> heads = jdbc.queryForList("""
                SELECT artifact_stream_id, confirmed_version_id
                FROM app.module_head WHERE case_id = ?::uuid AND module = ?
                """, caseId, module);
        if (heads.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "MODULE_NOT_FOUND", "模块 head 不存在");
        }
        UUID streamId = (UUID) heads.get(0).get("artifact_stream_id");

        // Ordered stream locks: conviction (upstream) before sentencing
        // (downstream), then the downstream head.  Other modules retain the
        // existing stream → head confirmation path.
        UUID convictionVersionId = null;
        if (ModulePolicies.SENTENCING.equals(module)) {
            convictionVersionId = requireEffectiveConviction(caseId);
        } else {
            lockFactsHead(caseId);
        }

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
        LegalAnalysisContext.requireCurrent(jdbc, caseId, latest);
        String outcome = jdbc.queryForObject(
                "SELECT outcome_status FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, latest);
        Boolean hasLegalBlockers = jdbc.queryForObject("""
                SELECT COALESCE(payload -> 'divergence', '[]'::jsonb) <> '[]'::jsonb
                    OR COALESCE(payload -> 'blockers', '[]'::jsonb) <> '[]'::jsonb
                FROM app.artifact_version WHERE artifact_version_id = ?
                """, Boolean.class, latest);
        if ("blocked".equals(outcome) || Boolean.TRUE.equals(hasLegalBlockers)) {
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
        if (ModulePolicies.SENTENCING.equals(module)) {
            requireSentencingDependency(caseId, latest, convictionVersionId);
        }
        registry.requireValid(jdbc, latest);
        jdbc.update("""
                UPDATE app.module_head
                SET confirmed_version_id = ?, stale = false, stale_reason = NULL, updated_at = now()
                WHERE case_id = ?::uuid AND module = ?
                """, latest, caseId, module);
        return latest;
    }
}
