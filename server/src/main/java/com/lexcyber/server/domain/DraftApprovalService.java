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
 * v1.3 §4.8.4 — Draft 批准。与模块确认同构，推进 draft_head.approved_version_id。
 * 批准前重校验依赖仍有效（不仅信生成时 gate）。
 */
@Service
public class DraftApprovalService {
    private final JdbcTemplate jdbc;

    public DraftApprovalService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean isEffectivelyApproved(UUID draftId) {
        List<Boolean> rows = jdbc.query("""
                SELECT approved_version_id IS NOT NULL AND NOT stale
                FROM app.draft_head WHERE draft_id = ?
                """, (rs, ignored) -> rs.getBoolean(1), draftId);
        return !rows.isEmpty() && rows.get(0);
    }

    public void requireEffectiveApproval(UUID draftId) {
        if (!isEffectivelyApproved(draftId)) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_NOT_APPROVED",
                    "文书尚无有效批准（未批准或已失效）");
        }
    }

    /**
     * 批准 draft stream 的 latest version；依赖快照重校验通过才推进 approved 指针。
     * 锁序 stream → head（与 publish 同序防互等死锁）；head 的 stream 绑定不可变可先做无锁读。
     */
    @Transactional
    public UUID approve(String caseId, UUID draftId, UUID actorId) {
        List<Map<String, Object>> heads = jdbc.queryForList("""
                SELECT artifact_stream_id, approved_version_id
                FROM app.draft_head WHERE draft_id = ? AND case_id = ?::uuid
                """, draftId, caseId);
        if (heads.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DRAFT_NOT_FOUND", "文书 head 不存在");
        }
        UUID streamId = (UUID) heads.get(0).get("artifact_stream_id");
        Map<String, Object> stream = jdbc.queryForMap("""
                SELECT latest_version_id FROM app.artifact_stream
                WHERE artifact_stream_id = ? FOR SHARE
                """, streamId);
        UUID latest = (UUID) stream.get("latest_version_id");
        jdbc.queryForMap("""
                SELECT approved_version_id FROM app.draft_head
                WHERE draft_id = ? AND case_id = ?::uuid FOR UPDATE
                """, draftId, caseId);
        if (latest == null) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_NOT_APPROVABLE", "文书尚无工件版本");
        }
        String outcome = jdbc.queryForObject(
                "SELECT outcome_status FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, latest);
        if ("blocked".equals(outcome)) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_BLOCKED", "blocked 版本不可批准");
        }
        Long staleDeps = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.artifact_facts_dependency afd
                JOIN app.facts_head h ON h.case_id = ?::uuid
                WHERE afd.artifact_version_id = ?
                  AND h.confirmed_facts_version_id IS DISTINCT FROM afd.facts_version_id
                """, Long.class, caseId, latest);
        if (staleDeps != null && staleDeps > 0L) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "依赖快照已失效，批准被阻断");
        }
        jdbc.update("""
                UPDATE app.draft_head
                SET approved_version_id = ?, stale = false, stale_reason = NULL, updated_at = now()
                WHERE draft_id = ? AND case_id = ?::uuid
                """, latest, draftId, caseId);
        return latest;
    }
}
