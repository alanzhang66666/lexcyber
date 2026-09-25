package com.lexcyber.server.domain;

import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * v1.3 §4.8.5 + ADR-0005 — stale 传播的唯一实现（INV-PIPE-003）。
 * 只修改 Head 有效性，不改历史 ArtifactVersion。
 * 依赖发现走正规化依赖表反向索引，不解析 dependency_snapshot JSON、不按模块顺序猜测。
 */
@Service
public class StalePropagationService {
    private final JdbcTemplate jdbc;

    public StalePropagationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 旧 FactsVersion 被新确认版本替代：直接消费者 + 递归下游全部 stale。 */
    public void propagateFactsSuperseded(String caseId, UUID oldFactsVersionId, String reason) {
        List<UUID> affected = jdbc.query("""
                WITH RECURSIVE affected(artifact_version_id) AS (
                    SELECT afd.artifact_version_id
                    FROM app.artifact_facts_dependency afd
                    WHERE afd.facts_version_id = ?
                    UNION
                    SELECT aad.artifact_version_id
                    FROM app.artifact_artifact_dependency aad
                    JOIN affected a ON aad.depends_on_artifact_version_id = a.artifact_version_id
                )
                SELECT artifact_version_id FROM affected
                """, (rs, ignored) -> rs.getObject(1, UUID.class), oldFactsVersionId);
        markStale(affected, reason);
    }

    /** 旧 ArtifactVersion 被替代：递归找下游消费者，其 Head 置 stale。 */
    public void propagateArtifactSuperseded(String caseId, UUID oldArtifactVersionId, String reason) {
        List<UUID> affected = jdbc.query("""
                WITH RECURSIVE affected(artifact_version_id) AS (
                    SELECT aad.artifact_version_id
                    FROM app.artifact_artifact_dependency aad
                    WHERE aad.depends_on_artifact_version_id = ?
                    UNION
                    SELECT aad.artifact_version_id
                    FROM app.artifact_artifact_dependency aad
                    JOIN affected a ON aad.depends_on_artifact_version_id = a.artifact_version_id
                )
                SELECT artifact_version_id FROM affected
                """, (rs, ignored) -> rs.getObject(1, UUID.class), oldArtifactVersionId);
        markStale(affected, reason);
    }

    /** Head 确认/批准指针仍指向受影响版本时置 stale；指针保留（INV-DOMAIN-002）。 */
    private void markStale(List<UUID> affectedVersionIds, String reason) {
        if (affectedVersionIds.isEmpty()) {
            return;
        }
        UUID[] ids = affectedVersionIds.toArray(UUID[]::new);
        jdbc.update("""
                UPDATE app.module_head
                SET stale = true, stale_reason = ?, updated_at = now()
                WHERE confirmed_version_id = ANY(?) AND NOT stale
                """, reason, ids);
        String draftReason = switch (reason) {
            case "facts_changed" -> "facts_changed";
            case "dependency_changed", "newer_version_published" -> reason;
            default -> "dependency_changed";
        };
        jdbc.update("""
                UPDATE app.draft_head
                SET stale = true, stale_reason = ?, updated_at = now()
                WHERE approved_version_id = ANY(?) AND NOT stale
                """, draftReason, ids);
    }
}
