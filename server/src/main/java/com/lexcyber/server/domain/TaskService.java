package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.ExecutionRequest;
import com.lexcyber.server.engine.EngineCapabilitiesClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TaskService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final boolean sentencingEnabled;
    private final IdentityService ids;
    private final EngineCapabilitiesClient capabilities;

    public TaskService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this(jdbc, objectMapper, false, null);
    }

    public TaskService(JdbcTemplate jdbc, ObjectMapper objectMapper,
                       @Value("${sentencing.enabled:false}") boolean sentencingEnabled) {
        this(jdbc, objectMapper, sentencingEnabled, null);
    }

    @Autowired
    public TaskService(JdbcTemplate jdbc, ObjectMapper objectMapper,
                       @Value("${sentencing.enabled:false}") boolean sentencingEnabled,
                       EngineCapabilitiesClient capabilities) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.sentencingEnabled = sentencingEnabled;
        this.capabilities = capabilities;
        this.ids = new IdentityService(jdbc);
    }

    @Transactional
    public TaskView create(TaskCreate request) {
        return createInternal(request, false);
    }

    /**
     * /v2 模块派发专用入口：跳过 /v1 公开口的静态 501 门闩（能力门闩由调用方
     * 前置校验——INV-GATE-002），但仍校验 taskType 属于已知集合。
     */
    @Transactional
    public TaskView createModuleTask(TaskCreate request) {
        return createInternal(request, true);
    }

    private TaskView createInternal(TaskCreate request, boolean moduleDispatch) {
        Map<String, Object> metadata = normalizeJson(
                request.metadata() == null ? Map.of() : request.metadata());
        if (moduleDispatch) {
            TaskPolicies.requireKnown(metadata);
            metadata.put("_dispatchOrigin", "v2");
        } else {
            metadata.remove("_dispatchOrigin");
            TaskPolicies.requireSupported(metadata, sentencingEnabled);
        }
        UUID id = UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        UUID executionId = UUID.randomUUID();
        UUID resultId = UUID.randomUUID();
        String caseId = ids.caseIdOrNull(request.caseId());
        String taskType = TaskPolicies.taskType(metadata);
        UUID factsVersionId = requireConfirmedFacts(taskType, caseId);
        ExecutionBinding binding = bindExecution(taskType, caseId, metadata, factsVersionId);
        String inputHash = hashInput(request.query(), caseId, request.sessionId(), metadata);
        ExecutionRequest envelope = new ExecutionRequest(id, executionId, requestId, resultId, 1, "workflow.output",
                request.query(), caseId, request.sessionId(), metadata, inputHash, "public-api-0.8",
                binding.streamId(), binding.inputSnapshotRef());
        jdbc.update("""
                INSERT INTO app.tasks(id, request_id, execution_id, case_id, session_id, query_text, status, current_stage, metadata_json)
                VALUES (?, ?, ?, ?::uuid, ?, ?, 'queued', 'accepted', ?::jsonb)
                """, id, requestId, executionId, caseId, request.sessionId(), request.query(), toJson(metadata));
        jdbc.update("INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json) VALUES (?, ?, 'execution.requested', ?::jsonb)",
                id, executionId, writeJson(envelope));
        return new TaskView(id, requestId, executionId, caseId, "queued", "accepted", null, null, null, OffsetDateTime.now(), OffsetDateTime.now());
    }

    @Transactional(readOnly = true)
    public String metadataTaskType(UUID taskId) {
        List<String> rows = jdbc.query(
                "SELECT metadata_json::text FROM app.tasks WHERE id = ?",
                (rs, ignored) -> rs.getString(1),
                taskId);
        if (rows.isEmpty() || rows.get(0) == null || rows.get(0).isBlank()) {
            return null;
        }
        return TaskPolicies.taskType(parseMap(rows.get(0)));
    }

    @Transactional(readOnly = true)
    public Optional<TaskView> find(UUID taskId) {
        return jdbc.query("""
                SELECT t.id, t.request_id, t.execution_id, t.case_id, t.status, t.current_stage, t.error_code, t.error, t.created_at, t.updated_at,
                       r.artifact_version_id AS result_id, r.version, r.schema_version AS result_type, r.output_hash AS content_hash
                FROM app.tasks t
                LEFT JOIN LATERAL (
                  SELECT artifact_version_id, version, schema_version, output_hash
                  FROM app.artifact_version WHERE execution_id = t.execution_id
                  ORDER BY version DESC LIMIT 1
                ) r ON TRUE
                WHERE t.id = ?
                """,
                this::map, taskId).stream().findFirst();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> result(UUID taskId) {
        List<Map<String, Object>> rows = jdbc.query("""
                SELECT v.artifact_version_id AS result_id, v.version, v.schema_version AS result_type,
                       v.output_hash AS content_hash, v.payload::text AS content_json
                FROM app.artifact_version v JOIN app.tasks t ON t.execution_id = v.execution_id
                WHERE t.id = ? ORDER BY v.version DESC LIMIT 1
                """, (rs, ignored) -> {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("resultId", rs.getObject("result_id", UUID.class));
            result.put("version", rs.getInt("version"));
            result.put("type", rs.getString("result_type"));
            result.put("contentHash", rs.getString("content_hash"));
            try {
                result.put("content", objectMapper.readValue(rs.getString("content_json"), Object.class));
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException("invalid stored result", ex);
            }
            return result;
        }, taskId);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "result not found");
        return rows.get(0);
    }

    @Transactional
    public TaskView retry(UUID taskId) {
        UUID executionId = UUID.randomUUID();
        Map<String, Object> task;
        try {
            task = jdbc.queryForMap("SELECT request_id, case_id, session_id, query_text, metadata_json, status FROM app.tasks WHERE id = ? FOR UPDATE", taskId);
        } catch (EmptyResultDataAccessException missing) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found", missing);
        }
        String status = String.valueOf(task.get("status"));
        if (!List.of("failed", "timed_out", "rejected").contains(status)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "task is not retryable");
        }
        // 结果序号 = 该任务的第 N 次派发（与 artifact version 解耦；INV-VERSION-005）
        int resultVersion = Optional.ofNullable(jdbc.queryForObject(
                "SELECT COUNT(*) + 1 FROM app.task_dispatch_outbox WHERE task_id = ? AND event_type = 'execution.requested'",
                Integer.class, taskId)).orElse(1);
        UUID resultId = UUID.randomUUID();
        Map<String, Object> metadata = parseMap(task.get("metadata_json"));
        String query = String.valueOf(task.get("query_text"));
        String caseId = task.get("case_id") == null ? null : String.valueOf(task.get("case_id"));
        String sessionId = task.get("session_id") == null ? null : String.valueOf(task.get("session_id"));
        UUID requestId = (UUID) task.get("request_id");
        String taskType = TaskPolicies.taskType(metadata);
        boolean v2 = isStructuredV2Metadata(metadata);
        if (v2) {
            requireV2Capability(metadata, taskType);
        } else {
            TaskPolicies.requireSupported(metadata, sentencingEnabled);
        }
        UUID factsVersionId = v2
                ? requireFrozenRetryInput(taskType, caseId, metadata)
                : requireConfirmedFacts(taskType, caseId);
        ExecutionBinding binding = bindExecution(taskType, caseId, metadata, factsVersionId);
        if (v2) validateOriginalBinding(taskId, binding, factsVersionId);
        String inputHash = hashInput(query, caseId, sessionId, metadata);
        ExecutionRequest envelope = new ExecutionRequest(taskId, executionId, requestId, resultId, resultVersion, "workflow.output",
                query, caseId, sessionId, metadata, inputHash, "public-api-0.8",
                binding.streamId(), binding.inputSnapshotRef());
        jdbc.update("UPDATE app.task_dispatch_outbox SET published_at=COALESCE(published_at, now()), last_error='superseded_by_retry' WHERE task_id=? AND published_at IS NULL", taskId);
        jdbc.update("UPDATE app.tasks SET execution_id = ?, status = 'queued', current_stage = 'retry_requested', error_code = NULL, error = NULL, updated_at = now() WHERE id = ?",
                executionId, taskId);
        jdbc.update("INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json) VALUES (?, ?, 'execution.requested', ?::jsonb)",
                taskId, executionId, writeJson(envelope));
        jdbc.update("UPDATE app.documents SET parse_status = 'queued', updated_at = now() WHERE parse_task_id = ?", taskId);
        return find(taskId).orElseThrow();
    }

    /**
     * 派发前绑定不可变输入（v1.3：执行不得读“当前可变状态”）。
     * 有案模块任务（sentencing/compliance/conviction）必须有 confirmed FactsVersion ——
     * 它是执行输入快照的权威引用；parse 任务以 document + sha256 为输入引用。
     */
    private boolean isStructuredV2Metadata(Map<String, Object> metadata) {
        String taskType = TaskPolicies.taskType(metadata);
        return ("v2".equals(metadata.get("_dispatchOrigin"))
                || (metadata.get("factsVersionId") != null && metadata.get("factsSnapshot") != null))
                && (TaskPolicies.COMPLIANCE_ANALYZE.equals(taskType)
                || TaskPolicies.CONVICTION_ANALYZE.equals(taskType)
                || TaskPolicies.SENTENCING_CALCULATE.equals(taskType)
                || TaskPolicies.DRAFT_RENDER.equals(taskType));
    }

    private void requireV2Capability(Map<String, Object> metadata, String taskType) {
        if (capabilities == null) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "MODULE_EXECUTION_UNAVAILABLE",
                    "v2 执行能力不可用");
        }
        if (TaskPolicies.DRAFT_RENDER.equals(taskType)) {
            if (!capabilities.templateAvailable(stringOrNull(metadata.get("docType")))) {
                throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "DRAFT_RENDER_UNAVAILABLE",
                        "文书渲染能力未启用");
            }
            return;
        }
        String module = stringOrNull(metadata.get("module"));
        if (module == null || !capabilities.moduleAvailable(module)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "MODULE_EXECUTION_UNAVAILABLE",
                    "模块执行能力不可用");
        }
    }

    private UUID requireFrozenRetryInput(String taskType, String caseId, Map<String, Object> metadata) {
        String raw = stringOrNull(metadata.get("factsVersionId"));
        if (raw == null || metadata.get("factsSnapshot") == null) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "重试缺少冻结事实快照");
        }
        UUID frozen;
        try {
            frozen = UUID.fromString(raw);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "重试事实快照引用无效", ex);
        }
        UUID current = requireConfirmedFacts(taskType, caseId);
        if (!frozen.equals(current)) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "案件事实已变更，必须重新派发");
        }
        if (TaskPolicies.SENTENCING_CALCULATE.equals(taskType)) {
            Object versions = metadata.get("artifactVersions");
            if (!(versions instanceof Map<?, ?> map) || map.size() != 1 || !map.containsKey("conviction")) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "量刑重试缺少冻结定罪版本");
            }
        }
        if (TaskPolicies.DRAFT_RENDER.equals(taskType) || TaskPolicies.SENTENCING_CALCULATE.equals(taskType)) {
            requireFrozenArtifactInputs(caseId, metadata);
        }
        return frozen;
    }

    private void requireFrozenArtifactInputs(String caseId, Map<String, Object> metadata) {
        Object versions = metadata.get("artifactVersions");
        if (!(versions instanceof Map<?, ?> map)) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "上游依赖快照缺失");
        }
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            UUID version;
            try {
                version = UUID.fromString(String.valueOf(entry.getValue()));
            } catch (IllegalArgumentException ex) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "上游依赖版本无效", ex);
            }
            // Keep the upstream version effective until the new outbox entry is
            // committed, using the same stream → head gate as first dispatch.
            try {
                UUID effective = new ModuleConfirmationService(jdbc)
                        .requireEffectiveArtifactVersion(caseId, String.valueOf(entry.getKey()));
                if (!version.equals(effective)) {
                    throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "上游版本已变更，必须重新派发");
                }
            } catch (ApiException unavailable) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "上游模块已失效，必须重新派发", unavailable);
            }
            Long valid = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM app.module_head h
                    JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                    WHERE h.case_id = ?::uuid AND h.module = ?
                      AND h.confirmed_version_id = ? AND NOT h.stale
                      AND s.latest_version_id = ?
                    """, Long.class, caseId, String.valueOf(entry.getKey()), version, version);
            if (valid == null || valid == 0L) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE", "上游模块已变更，必须重新派发");
            }
        }
    }

    private void validateOriginalBinding(UUID taskId, ExecutionBinding binding, UUID factsVersionId) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT payload_json ->> 'input_snapshot_ref' AS input_snapshot_ref,
                       payload_json ->> 'artifact_stream_id' AS artifact_stream_id
                FROM app.task_dispatch_outbox
                WHERE task_id = ? AND event_type = 'execution.requested'
                ORDER BY created_at ASC, id ASC LIMIT 1
                """, taskId);
        if (rows.isEmpty()
                || !Objects.equals("facts_version:" + factsVersionId, rows.get(0).get("input_snapshot_ref"))
                || !Objects.equals(binding.streamId() == null ? null : binding.streamId().toString(),
                                   rows.get(0).get("artifact_stream_id"))) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "任务原始输入绑定不一致，必须重新派发");
        }
    }

    private UUID requireConfirmedFacts(String taskType, String caseId) {
        if (caseId == null || caseId.isBlank()) {
            return null;
        }
        List<UUID> rows = jdbc.query(
                "SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?::uuid",
                (rs, ignored) -> rs.getObject(1, UUID.class),
                caseId);
        UUID factsVersionId = rows.isEmpty() ? null : rows.get(0);
        boolean requiresFacts = TaskPolicies.SENTENCING_CALCULATE.equals(taskType)
                || TaskPolicies.COMPLIANCE_ANALYZE.equals(taskType)
                || TaskPolicies.CONVICTION_ANALYZE.equals(taskType)
                || TaskPolicies.DRAFT_RENDER.equals(taskType);
        if (requiresFacts && factsVersionId == null) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_NOT_CONFIRMED", "该任务须先确认案件事实");
        }
        return factsVersionId;
    }

    /** (kind, scope_key) → stream 行锁创建/锁定；输入快照引用随执行入队，Engine 只按引用取输入。 */
    private ExecutionBinding bindExecution(String taskType, String caseId,
            Map<String, Object> metadata, UUID factsVersionId) {
        if (caseId == null || caseId.isBlank()) {
            return new ExecutionBinding(null, null);
        }
        ArtifactPublicationService publications =
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc));
        if (TaskPolicies.DOCUMENT_PARSE.equals(taskType)) {
            String documentId = stringOrNull(metadata.get("documentId"));
            if (documentId == null) {
                return new ExecutionBinding(null, null);
            }
            UUID streamId = publications.ensureStreamLocked(caseId, "parse", "document:" + documentId);
            String sha = stringOrNull(metadata.get("sha256"));
            String ref = "document:" + documentId + (sha == null ? "" : "@sha256:" + sha);
            return new ExecutionBinding(streamId, ref);
        }
        if (TaskPolicies.DRAFT_RENDER.equals(taskType)) {
            String docType = stringOrNull(metadata.get("docType"));
            if (docType == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "DOC_TYPE_MISSING", "draft.render 需要 metadata.docType");
            }
            String draftId = stringOrNull(metadata.get("draftId"));
            if (draftId == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "DRAFT_ID_MISSING", "draft.render 需要文书 UUID");
            }
            UUID streamId = jdbc.queryForObject("""
                    SELECT h.artifact_stream_id FROM app.draft_head h
                    JOIN app.case_drafts d ON d.id = h.draft_id
                    WHERE h.case_id = ?::uuid AND h.draft_id = ?::uuid AND d.draft_type = ?
                    """, UUID.class, caseId, draftId, docType);
            String ref = factsVersionId == null ? null : "facts_version:" + factsVersionId;
            return new ExecutionBinding(streamId, ref);
        }
        String module = switch (taskType == null ? "" : taskType) {
            case TaskPolicies.SENTENCING_CALCULATE -> "sentencing";
            case TaskPolicies.COMPLIANCE_ANALYZE -> "compliance";
            case TaskPolicies.CONVICTION_ANALYZE -> "conviction";
            default -> null;
        };
        if (module == null) {
            return new ExecutionBinding(null, null);
        }
        UUID streamId = publications.ensureStreamLocked(caseId, module, "module:" + module);
        String ref = factsVersionId == null ? null : "facts_version:" + factsVersionId;
        return new ExecutionBinding(streamId, ref);
    }

    private record ExecutionBinding(UUID streamId, String inputSnapshotRef) {
    }

    private static String stringOrNull(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private TaskView map(ResultSet rs, int ignored) throws SQLException {
        UUID resultId = rs.getObject("result_id", UUID.class);
        ResultRef result = resultId == null ? null : new ResultRef(resultId, rs.getInt("version"), rs.getString("result_type"), rs.getString("content_hash"), List.of());
        return new TaskView(rs.getObject("id", UUID.class), rs.getObject("request_id", UUID.class), rs.getObject("execution_id", UUID.class),
                rs.getString("case_id"), rs.getString("status"), rs.getString("current_stage"), result, rs.getString("error_code"), rs.getString("error"),
                rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class));
    }

    private String toJson(Map<String, Object> metadata) {
        return writeJson(metadata == null ? Map.of() : metadata);
    }

    private Map<String, Object> parseMap(Object value) {
        if (value == null) return Map.of();
        try {
            return objectMapper.readValue(String.valueOf(value), Map.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("invalid task metadata", ex);
        }
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("unable to serialize execution payload", ex);
        }
    }

    /**
     * 数值归一化：BigDecimal/BigInteger → double/long，保证 canonical JSON 与
     * Engine（Python json.dumps 把 JSON 数字一律解析为 float/int）逐字节一致。
     * 哈希与发送体必须使用同一份规范化数据，否则 input_hash 校验 409。
     */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> normalizeJson(Map<String, Object> metadata) {
        return (Map<String, Object>) normalizeValue(metadata);
    }

    private static Object normalizeValue(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> out = new LinkedHashMap<>();
            map.forEach((k, v) -> out.put(String.valueOf(k), normalizeValue(v)));
            return out;
        }
        if (value instanceof List<?> list) {
            List<Object> out = new ArrayList<>(list.size());
            for (Object item : list) out.add(normalizeValue(item));
            return out;
        }
        if (value instanceof BigDecimal bd) return bd.doubleValue();
        if (value instanceof java.math.BigInteger bi) return bi.longValue();
        return value;
    }

    private String hashInput(String query, String caseId, String sessionId, Map<String, Object> metadata) {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("case_id", caseId);
        input.put("metadata", metadata);
        input.put("query", query);
        input.put("session_id", sessionId);
        try {
            ObjectMapper canonical = objectMapper.copy()
                    .configure(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY, true)
                    .configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
            byte[] bytes = canonical.writeValueAsString(input).getBytes(StandardCharsets.UTF_8);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder result = new StringBuilder();
            for (byte item : digest) result.append(String.format("%02x", item & 0xff));
            return result.toString();
        } catch (Exception ex) {
            throw new IllegalStateException("unable to hash execution input", ex);
        }
    }
}
