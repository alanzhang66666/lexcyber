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
 * v1.3 §4.8.4 — Draft 批准。与模块确认同构，推进 draft_head.approved_version_id。
 * 批准前重校验依赖仍有效（不仅信生成时 gate）。
 */
@Service
public class DraftApprovalService {
    private final JdbcTemplate jdbc;
    private final EngineRegistryClient registry;

    public DraftApprovalService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        this.registry = new EngineRegistryClient();
    }

    @Autowired
    public DraftApprovalService(JdbcTemplate jdbc, EngineRegistryClient registry) {
        this.jdbc = jdbc;
        this.registry = registry;
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
        registry.lockBarrier(jdbc);
        LegalAnalysisContext.lockCase(jdbc, caseId);
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
        // Hold upstream pointers stable before locking the draft head. Publishers
        // lock upstream streams before propagating stale to downstream heads.
        // Acquiring these shares afterwards would both race and invert that order.
        jdbc.queryForList("""
                SELECT case_id FROM app.facts_head WHERE case_id = ?::uuid FOR SHARE
                """, caseId);
        jdbc.queryForList("""
                SELECT s.artifact_stream_id FROM app.artifact_stream s
                WHERE s.artifact_stream_id IN (
                    SELECT upstream.artifact_stream_id
                    FROM app.artifact_artifact_dependency d
                    JOIN app.artifact_version upstream
                      ON upstream.artifact_version_id = d.depends_on_artifact_version_id
                    WHERE d.artifact_version_id = ?
                )
                ORDER BY s.artifact_stream_id FOR SHARE OF s
                """, latest);
        jdbc.queryForMap("""
                SELECT approved_version_id FROM app.draft_head
                WHERE draft_id = ? AND case_id = ?::uuid FOR UPDATE
                """, draftId, caseId);
        if (latest == null) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_NOT_APPROVABLE", "文书尚无工件版本");
        }
        LegalAnalysisContext.requireCurrent(jdbc, caseId, latest);
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
        Long invalidV2Deps = jdbc.queryForObject("""
                WITH target AS (
                    SELECT v.artifact_version_id, v.schema_version, v.dependency_snapshot, s.case_id
                    FROM app.artifact_version v
                    JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                    WHERE v.artifact_version_id = ?
                ), elems AS (
                    SELECT e.value
                    FROM target t
                    CROSS JOIN LATERAL jsonb_array_elements(
                        CASE WHEN jsonb_typeof(t.dependency_snapshot -> 'artifacts') = 'array'
                             THEN t.dependency_snapshot -> 'artifacts'
                             ELSE '[]'::jsonb END) e
                )
                SELECT COUNT(*)
                FROM target t
                WHERE t.schema_version = 'draft.v2'
                  AND (
                      jsonb_typeof(t.dependency_snapshot -> 'artifacts') IS DISTINCT FROM 'array'
                      OR EXISTS (
                          SELECT 1 FROM elems e
                          WHERE jsonb_typeof(e.value) <> 'object'
                             OR NULLIF(e.value ->> 'module', '') IS NULL
                             OR NULLIF(e.value ->> 'artifactVersionId', '') IS NULL
                             OR NOT ((e.value ->> 'artifactVersionId') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
                             OR NOT EXISTS (
                                 SELECT 1
                                 FROM app.artifact_artifact_dependency d
                                 JOIN app.artifact_version upstream ON upstream.artifact_version_id = d.depends_on_artifact_version_id
                                 JOIN app.artifact_stream upstream_stream ON upstream_stream.artifact_stream_id = upstream.artifact_stream_id
                                 WHERE d.artifact_version_id = t.artifact_version_id
                                   AND upstream_stream.case_id = t.case_id
                                   AND upstream_stream.kind = e.value ->> 'module'
                                   AND d.depends_on_artifact_version_id =
                                       CASE WHEN (e.value ->> 'artifactVersionId') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                            THEN (e.value ->> 'artifactVersionId')::uuid END
                             )
                      )
                      OR EXISTS (
                          SELECT 1
                          FROM app.artifact_artifact_dependency d
                          WHERE d.artifact_version_id = t.artifact_version_id
                            AND NOT EXISTS (
                                SELECT 1 FROM elems e
                                WHERE (e.value ->> 'artifactVersionId') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                  AND CASE WHEN (e.value ->> 'artifactVersionId') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                           THEN (e.value ->> 'artifactVersionId')::uuid END = d.depends_on_artifact_version_id
                            )
                      )
                  )
                """, Long.class, latest);
        if (invalidV2Deps != null && invalidV2Deps > 0L) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "draft.v2 上游工件依赖未按冻结版本精确绑定，批准被阻断");
        }
        registry.requireValid(jdbc, latest);
        Long staleArtifactDeps = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM app.artifact_artifact_dependency d
                WHERE d.artifact_version_id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM app.artifact_version upstream
                      JOIN app.artifact_stream stream
                        ON stream.artifact_stream_id = upstream.artifact_stream_id
                      JOIN app.module_head module_head
                        ON module_head.artifact_stream_id = upstream.artifact_stream_id
                      WHERE upstream.artifact_version_id = d.depends_on_artifact_version_id
                        AND stream.latest_version_id = d.depends_on_artifact_version_id
                        AND module_head.confirmed_version_id = d.depends_on_artifact_version_id
                        AND NOT module_head.stale
                        AND upstream.outcome_status <> 'blocked'
                  )
                """, Long.class, latest);
        if (staleArtifactDeps != null && staleArtifactDeps > 0L) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "上游工件依赖已失效或未确认，批准被阻断");
        }
        jdbc.update("""
                UPDATE app.draft_head
                SET approved_version_id = ?, stale = false, stale_reason = NULL, updated_at = now()
                WHERE draft_id = ? AND case_id = ?::uuid
                """, latest, draftId, caseId);
        return latest;
    }
}
