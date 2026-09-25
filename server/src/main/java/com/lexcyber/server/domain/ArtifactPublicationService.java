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
 * v1.3 §4.8.2 — ArtifactVersion 发布的唯一实现。
 * execution_publication 是发布幂等的权威绑定（ADR-0001）；
 * 手工发布（execution_id IS NULL）供 /v1 模块 PUT 与导入器使用。
 * 版本号只经 artifact_stream.next_version 在行锁内推进。
 */
@Service
public class ArtifactPublicationService {
    private final JdbcTemplate jdbc;
    private final StalePropagationService stale;

    public ArtifactPublicationService(JdbcTemplate jdbc, StalePropagationService stale) {
        this.jdbc = jdbc;
        this.stale = stale;
    }

    public record PublishRequest(
            String caseId,
            String kind,                    // parse|compliance|conviction|sentencing|draft
            String scopeKey,                // 服务端规范值：document:{id} / module:{m} / draft:{id}
            String schemaVersion,
            String outcomeStatus,           // calculated|blocked|not_applicable
            String payloadJson,             // 已序列化 jsonb
            String blockersJson,            // 已序列化 jsonb array
            String dependencySnapshotJson,  // 审计快照
            UUID factsVersionId,            // 事实依赖（可空）
            List<UUID> artifactDependencies,
            List<ExternalDependency> externalDependencies,
            UUID executionId,               // 手工发布为 null
            String completionIdentity,
            String outputHash) {
    }

    public record ExternalDependency(String kind, String key, String version) {
    }

    public record PublishResult(UUID artifactVersionId, int version, boolean replayed) {
    }

    @Transactional
    public PublishResult publish(PublishRequest req) {
        // §4.8.2 step 3 — execution_publication 幂等（锁外快速路径）
        if (req.executionId() != null) {
            UUID replay = publishedVersionOrThrow(req.executionId(), req.outputHash());
            if (replay != null) {
                return new PublishResult(replay, -1, true);
            }
        }

        UUID streamId = ensureStreamLocked(req.caseId(), req.kind(), req.scopeKey());
        // 锁内重查：并发双发在 stream 行锁上串行化，后到者在这里看到先到的绑定
        if (req.executionId() != null) {
            UUID replay = publishedVersionOrThrow(req.executionId(), req.outputHash());
            if (replay != null) {
                return new PublishResult(replay, -1, true);
            }
        }
        Map<String, Object> stream = jdbc.queryForMap("""
                SELECT latest_version_id, next_version FROM app.artifact_stream
                WHERE artifact_stream_id = ?
                """, streamId);
        int version = ((Number) stream.get("next_version")).intValue();
        UUID oldLatest = (UUID) stream.get("latest_version_id");
        UUID versionId = UUID.randomUUID();
        String outputHash = req.outputHash() != null ? req.outputHash()
                : FactsBaselineService.sha256(req.payloadJson());

        // steps 6-7：version + 依赖同事务写入（INV-DB-DEP-001）
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, blockers, dependency_snapshot,
                    execution_id, output_hash)
                VALUES (?, ?, ?, ?, ?, ?::jsonb, COALESCE(?::jsonb, '[]'::jsonb), ?::jsonb, ?, ?)
                """, versionId, streamId, version, req.schemaVersion(), req.outcomeStatus(),
                req.payloadJson(), req.blockersJson(),
                req.dependencySnapshotJson() == null ? "{}" : req.dependencySnapshotJson(),
                req.executionId(), outputHash);
        if (req.factsVersionId() != null) {
            jdbc.update("""
                    INSERT INTO app.artifact_facts_dependency(artifact_version_id, facts_version_id)
                    VALUES (?, ?)
                    """, versionId, req.factsVersionId());
        }
        if (req.artifactDependencies() != null) {
            for (UUID dep : req.artifactDependencies()) {
                if (dep == null || dep.equals(versionId)) {
                    continue;
                }
                Long sameCase = jdbc.queryForObject("""
                        SELECT COUNT(*) FROM app.artifact_version v
                        JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                        WHERE v.artifact_version_id = ? AND s.case_id = ?::uuid
                        """, Long.class, dep, req.caseId());
                if (sameCase == null || sameCase == 0L) {
                    throw new ApiException(HttpStatus.CONFLICT, "CROSS_CASE_DEPENDENCY",
                            "工件依赖跨案件，拒绝发布");
                }
                jdbc.update("""
                        INSERT INTO app.artifact_artifact_dependency(
                            artifact_version_id, depends_on_artifact_version_id)
                        VALUES (?, ?)
                        """, versionId, dep);
            }
        }
        if (req.externalDependencies() != null) {
            for (ExternalDependency dep : req.externalDependencies()) {
                if (!List.of("rule", "legal_source", "template").contains(dep.kind())) {
                    throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                            "unsupported dependency_kind");
                }
                jdbc.update("""
                        INSERT INTO app.artifact_external_dependency(
                            artifact_version_id, dependency_kind, dependency_key, dependency_version)
                        VALUES (?, ?, ?, ?)
                        """, versionId, dep.kind(), dep.key(), dep.version());
            }
        }

        // step 8：推进 latest + next_version（行锁内，不用 MAX+1）
        jdbc.update("""
                UPDATE app.artifact_stream
                SET latest_version_id = ?, next_version = next_version + 1, updated_at = now()
                WHERE artifact_stream_id = ?
                """, versionId, streamId);

        // step 9：Head 保留确认/批准指针并置 stale（INV-DOMAIN-002）
        if ("draft".equals(req.kind())) {
            jdbc.update("""
                    UPDATE app.draft_head
                    SET stale = true, stale_reason = 'newer_version_published', updated_at = now()
                    WHERE artifact_stream_id = ? AND approved_version_id IS NOT NULL AND NOT stale
                    """, streamId);
        } else {
            jdbc.update("""
                    UPDATE app.module_head
                    SET stale = true, stale_reason = 'newer_version_published', updated_at = now()
                    WHERE artifact_stream_id = ? AND confirmed_version_id IS NOT NULL AND NOT stale
                    """, streamId);
        }

        // step 10：本 stream 旧版本上 pending 的复核置 superseded
        jdbc.update("""
                UPDATE app.review_records
                SET status = 'superseded', decided_at = COALESCE(decided_at, now())
                WHERE status = 'pending' AND artifact_version_id IN (
                    SELECT artifact_version_id FROM app.artifact_version
                    WHERE artifact_stream_id = ? AND artifact_version_id <> ?)
                """, streamId, versionId);

        // step 11：发布绑定
        if (req.executionId() != null) {
            jdbc.update("""
                    INSERT INTO app.execution_publication(
                        execution_id, artifact_version_id, completion_identity, output_hash)
                    VALUES (?, ?, ?, ?)
                    """, req.executionId(), versionId,
                    req.completionIdentity() == null ? "" : req.completionIdentity(), outputHash);
        }

        // 旧 latest 被替代 → 递归下游 stale
        if (oldLatest != null && !oldLatest.equals(versionId)) {
            stale.propagateArtifactSuperseded(req.caseId(), oldLatest, "dependency_changed");
        }
        return new PublishResult(versionId, version, false);
    }

    /**
     * execution_publication 幂等判定：同 execution 同 hash → 返回已发布版本 id；
     * 同 execution 异 hash → 审计后抛 409；未发布 → null。
     * 跨 stream 复用同一 execution_id 属于契约违例，由 ux_artifact_version_execution 兜底。
     */
    private UUID publishedVersionOrThrow(UUID executionId, String outputHash) {
        List<Map<String, Object>> bound = jdbc.queryForList(
                "SELECT artifact_version_id, output_hash FROM app.execution_publication WHERE execution_id = ?",
                executionId);
        if (bound.isEmpty()) {
            return null;
        }
        Map<String, Object> row = bound.get(0);
        if (outputHash != null && outputHash.equals(row.get("output_hash"))) {
            return (UUID) row.get("artifact_version_id");
        }
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES ('system', 'publication.hash_conflict', 'execution', ?,
                        jsonb_build_object('executionId', ?::text))
                """, executionId.toString(), executionId.toString());
        throw new ApiException(HttpStatus.CONFLICT, "PUBLICATION_HASH_MISMATCH",
                "同一 execution 的输出哈希不一致，发布被阻断");
    }

    /** stream 定位：scope_key 由服务端生成（§4.6.4）；调用方已持有 case 行锁。
     *  模块 stream 同时保证 module_head 行存在（head 是模块的唯一指针位置）。 */
    public UUID ensureStreamLocked(String caseId, String kind, String scopeKey) {
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key)
                VALUES (?, ?::uuid, ?, ?)
                ON CONFLICT (case_id, kind, scope_key) DO NOTHING
                """, UUID.randomUUID(), caseId, kind, scopeKey);
        UUID streamId = jdbc.queryForObject("""
                SELECT artifact_stream_id FROM app.artifact_stream
                WHERE case_id = ?::uuid AND kind = ? AND scope_key = ?
                FOR UPDATE
                """, UUID.class, caseId, kind, scopeKey);
        if (scopeKey.equals("module:" + kind)
                && List.of("compliance", "conviction", "sentencing").contains(kind)) {
            jdbc.update("""
                    INSERT INTO app.module_head(case_id, module, artifact_stream_id)
                    VALUES (?::uuid, ?, ?)
                    ON CONFLICT (case_id, module) DO NOTHING
                    """, caseId, kind, streamId);
        }
        return streamId;
    }
}
