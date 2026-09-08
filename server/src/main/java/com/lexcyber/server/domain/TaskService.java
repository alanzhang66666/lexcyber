package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.lexcyber.server.engine.ExecutionRequest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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

    public TaskService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this(jdbc, objectMapper, false);
    }

    @Autowired
    public TaskService(JdbcTemplate jdbc, ObjectMapper objectMapper,
                       @Value("${sentencing.enabled:false}") boolean sentencingEnabled) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.sentencingEnabled = sentencingEnabled;
    }

    @Transactional
    public TaskView create(TaskCreate request) {
        Map<String, Object> metadata = request.metadata() == null ? Map.of() : request.metadata();
        TaskPolicies.requireSupported(metadata, sentencingEnabled);
        UUID id = UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        UUID executionId = UUID.randomUUID();
        UUID resultId = UUID.randomUUID();
        String caseId = request.caseId() == null ? "" : request.caseId();
        String inputHash = hashInput(request.query(), caseId, request.sessionId(), metadata);
        ExecutionRequest envelope = new ExecutionRequest(id, executionId, requestId, resultId, 1, "workflow.output",
                request.query(), caseId, request.sessionId(), metadata, inputHash, "public-api-0.3");
        jdbc.update("""
                INSERT INTO app.tasks(id, request_id, execution_id, case_id, session_id, query_text, status, current_stage, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, 'queued', 'accepted', ?::jsonb)
                """, id, requestId, executionId, caseId, request.sessionId(), request.query(), toJson(metadata));
        jdbc.update("INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json) VALUES (?, ?, 'execution.requested', ?::jsonb)",
                id, executionId, writeJson(envelope));
        return new TaskView(id, requestId, executionId, caseId, "queued", "accepted", null, null, null, OffsetDateTime.now(), OffsetDateTime.now());
    }

    @Transactional(readOnly = true)
    public Optional<TaskView> find(UUID taskId) {
        return jdbc.query("""
                SELECT t.id, t.request_id, t.execution_id, t.case_id, t.status, t.current_stage, t.error_code, t.error, t.created_at, t.updated_at,
                       r.result_id, r.version, r.result_type, r.content_hash
                FROM app.tasks t
                LEFT JOIN LATERAL (
                  SELECT result_id, version, result_type, content_hash
                  FROM app.result_versions WHERE task_id=t.id AND execution_id=t.execution_id
                  ORDER BY version DESC LIMIT 1
                ) r ON TRUE
                WHERE t.id = ?
                """,
                this::map, taskId).stream().findFirst();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> result(UUID taskId) {
        List<Map<String, Object>> rows = jdbc.query("""
                SELECT r.result_id, r.version, r.result_type, r.content_hash, r.content_json
                FROM app.result_versions r JOIN app.tasks t ON t.id=r.task_id AND t.execution_id=r.execution_id
                WHERE r.task_id=? ORDER BY r.version DESC LIMIT 1
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
            throw new IllegalStateException("task is not retryable or does not exist");
        }
        int resultVersion = Optional.ofNullable(jdbc.queryForObject("SELECT COALESCE(MAX(version), 0) + 1 FROM app.result_versions WHERE task_id = ?", Integer.class, taskId)).orElse(1);
        UUID resultId = UUID.randomUUID();
        Map<String, Object> metadata = parseMap(task.get("metadata_json"));
        TaskPolicies.requireSupported(metadata, sentencingEnabled);
        String query = String.valueOf(task.get("query_text"));
        String caseId = task.get("case_id") == null ? null : String.valueOf(task.get("case_id"));
        String sessionId = task.get("session_id") == null ? null : String.valueOf(task.get("session_id"));
        UUID requestId = (UUID) task.get("request_id");
        String inputHash = hashInput(query, caseId, sessionId, metadata);
        ExecutionRequest envelope = new ExecutionRequest(taskId, executionId, requestId, resultId, resultVersion, "workflow.output",
                query, caseId, sessionId, metadata, inputHash, "public-api-0.3");
        jdbc.update("UPDATE app.task_dispatch_outbox SET published_at=COALESCE(published_at, now()), last_error='superseded_by_retry' WHERE task_id=? AND published_at IS NULL", taskId);
        jdbc.update("UPDATE app.tasks SET execution_id = ?, status = 'queued', current_stage = 'retry_requested', error_code = NULL, error = NULL, updated_at = now() WHERE id = ?",
                executionId, taskId);
        jdbc.update("INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json) VALUES (?, ?, 'execution.requested', ?::jsonb)",
                taskId, executionId, writeJson(envelope));
        jdbc.update("UPDATE app.documents SET parse_status = 'queued', updated_at = now() WHERE parse_task_id = ?", taskId);
        return find(taskId).orElseThrow();
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
