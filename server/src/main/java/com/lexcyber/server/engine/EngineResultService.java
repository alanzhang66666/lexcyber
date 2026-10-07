package com.lexcyber.server.engine;

import com.lexcyber.server.domain.ArtifactPublicationService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Applies callback and reconciliation results idempotently at the app boundary.
 * 结果落库走 ArtifactPublicationService（execution_publication 幂等，ADR-0001），
 * 不再写 result_versions；waiting_review 时在该 artifact_version 上开复核。
 */
@Service
public class EngineResultService {
    private final JdbcTemplate jdbc;
    private final ArtifactPublicationService artifacts;
    private final com.fasterxml.jackson.databind.ObjectMapper objectMapper;

    public EngineResultService(JdbcTemplate jdbc, ArtifactPublicationService artifacts,
            com.fasterxml.jackson.databind.ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.artifacts = artifacts;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> accept(ResultEnvelope payload) {
        if (payload == null || payload.executionId() == null || payload.taskId() == null || payload.requestId() == null
                || payload.resultId() == null || payload.status() == null || payload.currentStage() == null
                || payload.resultType() == null
                || !SetOfStatuses.contains(payload.status())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid execution status");
        }
        Map<String, Object> task;
        try {
            task = jdbc.queryForMap("SELECT id, request_id, execution_id FROM app.tasks WHERE id = ? FOR UPDATE", payload.taskId());
        } catch (EmptyResultDataAccessException missing) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found", missing);
        }
        UUID taskId = (UUID) task.get("id");
        UUID requestId = (UUID) task.get("request_id");
        UUID currentExecution = (UUID) task.get("execution_id");
        if (!payload.requestId().equals(requestId)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "execution request does not belong to task");
        }
        boolean current = payload.executionId().equals(currentExecution);

        Long expected = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.task_dispatch_outbox
                WHERE task_id=? AND execution_id=?
                  AND payload_json->>'result_id'=?
                  AND payload_json->>'result_version'=?
                """, Long.class, taskId, payload.executionId(), String.valueOf(payload.resultId()), String.valueOf(payload.resultVersion()));
        if (expected == null || expected == 0L) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "execution result is not associated with task request");
        }

        boolean executionAlreadyPublished = current && Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM app.execution_publication WHERE execution_id = ?)",
                Boolean.class, payload.executionId()));
        UUID publishedVersionId = null;
        if (payload.contentJson() != null) {
            if (payload.resultVersion() < 1 || payload.contentHash() == null
                    || !constantTimeHash(payload.contentJson(), payload.contentHash())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "result content hash mismatch");
            }
            // A late completion may still be accepted for audit purposes, but it
            // must never publish a new artifact or move the current stream head.
            if (current && "completed".equals(payload.status())) {
                publishedVersionId = publishParseArtifact(taskId, payload);
            }
        }

        if (current && !executionAlreadyPublished) {
            // v1.3：execution 终态只有 completed/failed；human_review_required 经
            // output_envelope 传入，映射为 app.tasks 的展示态 waiting_review（INV-RUNTIME-001）。
            String taskStatus = taskStatusOf(payload);
            jdbc.update("UPDATE app.tasks SET status=?, current_stage=?, error_code=?, error=?, updated_at=now() WHERE id=? AND execution_id=?",
                    taskStatus, payload.currentStage(), payload.errorCode(), payload.errorMessage(), taskId, payload.executionId());
            jdbc.update("UPDATE app.documents SET parse_status=?, updated_at=now() WHERE parse_task_id=?", taskStatus, taskId);
            if ("waiting_review".equals(taskStatus) && publishedVersionId != null) {
                String caseId = caseIdOf(taskId);
                // Callback delivery is replayed by the engine/outbox.  An
                // existing review, including an already decided one, is the
                // idempotency record: never reopen or duplicate it.
                jdbc.update("""
                        INSERT INTO app.review_records(review_id, artifact_version_id, case_id, status, actor_id)
                        SELECT ?, ?, ?::uuid, 'pending',
                               (SELECT owner_account_id FROM app.cases WHERE id = ?::uuid)
                        WHERE NOT EXISTS (
                            SELECT 1 FROM app.review_records WHERE artifact_version_id = ?
                        )
                        """, UUID.randomUUID(), publishedVersionId, caseId, caseId, publishedVersionId);
            }
        }
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES ('engine-service', 'result.accepted', 'task', ?,
                        jsonb_build_object('taskId', ?::text, 'requestId', ?::text, 'executionId', ?::text, 'resultId', ?::text,
                                           'resultVersion', ?, 'status', ?, 'stale', ?))
                """, taskId.toString(), taskId.toString(), requestId.toString(), payload.executionId().toString(), payload.resultId().toString(),
                payload.resultVersion(), payload.status(), !current);
        return Map.of("status", "accepted", "executionId", payload.executionId(), "stale", !current);
    }

    /** parse 结果 → artifact_version；同一 execution 重放返回既有 version（execution_publication）。 */
    private UUID publishParseArtifact(UUID taskId, ResultEnvelope payload) {
        List<Map<String, Object>> docs = jdbc.queryForList("""
                SELECT d.id AS document_id, d.case_id
                FROM app.documents d WHERE d.parse_task_id = ?
                """, taskId);
        if (docs.isEmpty()) {
            // 模块/文书任务：按派发时绑定的 (kind, scope_key) stream 发布
            return publishModuleArtifact(taskId, payload);
        }
        UUID documentId = (UUID) docs.get(0).get("document_id");
        String caseId = String.valueOf(docs.get(0).get("case_id"));
        var result = artifacts.publish(new ArtifactPublicationService.PublishRequest(
                caseId, "parse", "document:" + documentId, payload.resultType(),
                "calculated", payload.contentJson(), null, "{}",
                null, List.of(), List.of(),
                payload.executionId(), payload.completionIdentity(), payload.contentHash()));
        return result.artifactVersionId();
    }

    /**
     * 模块/文书执行结果 → artifact_version。kind/scope_key 与 TaskService.bindExecution
     * 派发绑定一致；schema_version/status/依赖快照取自引擎产出 payload 自身。
     */
    @SuppressWarnings("unchecked")
    private UUID publishModuleArtifact(UUID taskId, ResultEnvelope payload) {
        Map<String, Object> task;
        try {
            task = jdbc.queryForMap(
                    """
                    SELECT t.case_id,
                           COALESCE(o.payload_json->'metadata', t.metadata_json)::text AS metadata_json,
                           o.payload_json->>'artifact_stream_id' AS bound_stream_id,
                           o.payload_json->>'input_snapshot_ref' AS input_snapshot_ref
                    FROM app.tasks t JOIN app.task_dispatch_outbox o ON o.task_id = t.id
                    WHERE t.id = ? AND o.execution_id = ?
                    """, taskId, payload.executionId());
        } catch (EmptyResultDataAccessException missing) {
            return null;
        }
        if (task.get("case_id") == null) {
            return null;
        }
        String caseId = task.get("case_id").toString();
        Map<String, Object> metadata;
        Map<String, Object> content;
        try {
            metadata = objectMapper.readValue(String.valueOf(task.get("metadata_json")), Map.class);
            content = objectMapper.readValue(payload.contentJson(), Map.class);
        } catch (Exception ex) {
            throw new IllegalStateException("invalid stored task metadata or result payload", ex);
        }
        String taskType = metadata.get("taskType") == null ? null : String.valueOf(metadata.get("taskType"));
        String kind;
        String scopeKey;
        switch (taskType == null ? "" : taskType) {
            case "compliance.analyze" -> { kind = "compliance"; scopeKey = "module:compliance"; }
            case "conviction.analyze" -> { kind = "conviction"; scopeKey = "module:conviction"; }
            case "sentencing.calculate" -> { kind = "sentencing"; scopeKey = "module:sentencing"; }
            case "draft.render" -> {
                kind = "draft";
                if (task.get("bound_stream_id") != null) {
                    scopeKey = jdbc.queryForObject("""
                            SELECT s.scope_key FROM app.artifact_stream s
                            JOIN app.draft_head h ON h.artifact_stream_id = s.artifact_stream_id
                            WHERE s.artifact_stream_id = ?::uuid AND s.case_id = ?::uuid AND s.kind = 'draft'
                            """, String.class, task.get("bound_stream_id"), caseId);
                } else if (metadata.get("draftId") != null) {
                    scopeKey = "draft:" + UUID.fromString(String.valueOf(metadata.get("draftId")));
                } else {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "draft result has no descriptor binding");
                }
            }
            default -> { return null; }
        }
        String schemaVersion = content.get("schema_version") == null
                ? payload.resultType() : String.valueOf(content.get("schema_version"));
        String outcome = content.get("status") == null ? "calculated" : String.valueOf(content.get("status"));
        if (!List.of("calculated", "blocked", "not_applicable").contains(outcome)) {
            outcome = "calculated";
        }
        String blockersJson = writeJson(content.getOrDefault("blockers", List.of()));
        Map<String, Object> dep = content.get("dependency_snapshot") instanceof Map<?, ?> m
                ? (Map<String, Object>) m : Map.of();
        UUID factsVersionId = dep.get("facts_version_id") == null ? null
                : UUID.fromString(String.valueOf(dep.get("facts_version_id")));

        List<ArtifactPublicationService.ExternalDependency> external = new java.util.ArrayList<>();
        if (dep.get("rules") instanceof List<?> rules) {
            for (Object rule : rules) {
                if (rule instanceof Map<?, ?> r && r.get("ruleId") != null) {
                    external.add(new ArtifactPublicationService.ExternalDependency(
                            "rule", String.valueOf(r.get("ruleId")),
                            r.get("ruleVersion") == null ? "" : String.valueOf(r.get("ruleVersion"))));
                }
            }
        }
        if (dep.get("template") instanceof Map<?, ?> t && t.get("templateId") != null) {
            external.add(new ArtifactPublicationService.ExternalDependency(
                    "template", String.valueOf(t.get("templateId")),
                    t.get("templateVersion") == null ? "" : String.valueOf(t.get("templateVersion"))));
        }
        if (dep.get("sources") instanceof List<?> sources) {
            for (Object source : sources) {
                external.add(new ArtifactPublicationService.ExternalDependency(
                        "legal_source", String.valueOf(source), ""));
            }
        }

        // Bind exactly the versions used by rendering, never the heads at completion time.
        List<UUID> artifactDeps = new java.util.ArrayList<>();
        if ("draft".equals(kind)) {
            Map<?, ?> frozen = metadata.get("artifactVersions") instanceof Map<?, ?> refs ? refs : Map.of();
            List<?> returned = dep.get("artifacts") instanceof List<?> refs ? refs : List.of();
            if (returned.size() != frozen.size()) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "render dependency snapshot mismatch");
            }
            java.util.Set<String> modules = new java.util.HashSet<>();
            for (Object entry : returned) {
                if (!(entry instanceof Map<?, ?> ref) || ref.get("module") == null
                        || ref.get("artifactVersionId") == null) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "render dependency version is missing");
                }
                String module = String.valueOf(ref.get("module"));
                String version = String.valueOf(ref.get("artifactVersionId"));
                if (!modules.add(module) || !version.equals(String.valueOf(frozen.get(module)))) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "render dependency snapshot mismatch");
                }
                UUID versionId = UUID.fromString(version);
                Long owned = jdbc.queryForObject("""
                        SELECT COUNT(*) FROM app.artifact_version v
                        JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                        WHERE v.artifact_version_id = ? AND s.case_id = ?::uuid
                          AND s.kind = ? AND s.scope_key = ?
                        """, Long.class, versionId, caseId, module, "module:" + module);
                if (owned == null || owned != 1L) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "render dependency belongs to another stream");
                }
                artifactDeps.add(versionId);
            }
            String inputRef = String.valueOf(task.get("input_snapshot_ref"));
            if (factsVersionId == null || !inputRef.equals("facts_version:" + factsVersionId)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "render facts snapshot mismatch");
            }
        }
        if ("sentencing".equals(kind) && metadata.get("artifactVersions") instanceof Map<?, ?> frozen) {
            Object frozenConviction = frozen.get("conviction");
            List<?> returned = dep.get("artifacts") instanceof List<?> refs ? refs : List.of();
            if (frozenConviction == null || returned.size() != 1) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "sentencing dependency snapshot mismatch");
            }
            Object entry = returned.get(0);
            if (!(entry instanceof Map<?, ?> ref)
                    || !"conviction".equals(String.valueOf(ref.get("module")))
                    || !String.valueOf(frozenConviction).equals(String.valueOf(ref.get("artifactVersionId")))) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "sentencing dependency snapshot mismatch");
            }
            UUID convictionVersionId;
            try {
                convictionVersionId = UUID.fromString(String.valueOf(frozenConviction));
            } catch (IllegalArgumentException invalidId) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "sentencing dependency snapshot mismatch", invalidId);
            }
            Long owned = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM app.artifact_version v
                    JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                    WHERE v.artifact_version_id = ? AND s.case_id = ?::uuid
                      AND s.kind = 'conviction' AND s.scope_key = 'module:conviction'
                    """, Long.class, convictionVersionId, caseId);
            if (owned == null || owned != 1L) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "sentencing dependency belongs to another stream");
            }
            Object frozenFacts = metadata.get("factsVersionId");
            String inputRef = String.valueOf(task.get("input_snapshot_ref"));
            if (frozenFacts == null || factsVersionId == null
                    || !String.valueOf(frozenFacts).equals(String.valueOf(factsVersionId))
                    || !inputRef.equals("facts_version:" + frozenFacts)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "sentencing facts snapshot mismatch");
            }
            artifactDeps.add(convictionVersionId);
        }

        var result = artifacts.publish(new ArtifactPublicationService.PublishRequest(
                caseId, kind, scopeKey, schemaVersion, outcome, payload.contentJson(),
                blockersJson, writeJson(dep), factsVersionId, artifactDeps, external,
                payload.executionId(), payload.completionIdentity(), payload.contentHash()));
        return result.artifactVersionId();
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception ex) {
            throw new IllegalStateException("unable to serialize result payload", ex);
        }
    }

    /** execution 终态 → tasks 展示态：engine 不再发 waiting_review/timed_out（INV-RUNTIME-001），
     *  兼容期仍接受旧值。 */
    private static String taskStatusOf(ResultEnvelope payload) {
        if ("completed".equals(payload.status())
                && payload.outputEnvelope() != null
                && Boolean.TRUE.equals(payload.outputEnvelope().get("human_review_required"))) {
            return "waiting_review";
        }
        if ("timed_out".equals(payload.status())) {
            return "failed";
        }
        return payload.status();
    }

    private String caseIdOf(UUID taskId) {
        Object value = jdbc.queryForObject("SELECT case_id FROM app.tasks WHERE id = ?", Object.class, taskId);
        return value == null ? null : value.toString();
    }

    private boolean constantTimeHash(String content, String expected) {
        byte[] actual = digest(content);
        byte[] supplied;
        try {
            supplied = hex(expected);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        return MessageDigest.isEqual(actual, supplied);
    }

    private byte[] digest(String content) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }

    private byte[] hex(String value) {
        if (value.length() != 64) throw new IllegalArgumentException("invalid hash length");
        byte[] result = new byte[32];
        for (int i = 0; i < result.length; i++) {
            int high = Character.digit(value.charAt(i * 2), 16);
            int low = Character.digit(value.charAt(i * 2 + 1), 16);
            if (high < 0 || low < 0) throw new IllegalArgumentException("invalid hash");
            result[i] = (byte) ((high << 4) + low);
        }
        return result;
    }

    private static final java.util.Set<String> SetOfStatuses = java.util.Set.of("completed", "waiting_review", "failed", "timed_out");
}
