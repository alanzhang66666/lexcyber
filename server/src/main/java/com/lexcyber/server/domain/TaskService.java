package com.lexcyber.server.domain;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {
    private final JdbcTemplate jdbc;

    public TaskService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public TaskView create(TaskCreate request) {
        UUID id = UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        UUID executionId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.tasks(id, request_id, execution_id, case_id, query_text, status, current_stage, metadata_json)
                VALUES (?, ?, ?, ?, ?, 'queued', 'accepted', ?::jsonb)
                """, id, requestId, executionId, request.caseId(), request.query(), toJson(request.metadata()));
        jdbc.update("INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json) VALUES (?, ?, 'execution.requested', ?::jsonb)",
                id, executionId, "{\"taskId\":\"" + id + "\",\"executionId\":\"" + executionId + "\"}");
        return new TaskView(id, requestId, executionId, request.caseId(), "queued", "accepted", null, null, OffsetDateTime.now(), OffsetDateTime.now());
    }

    @Transactional(readOnly = true)
    public Optional<TaskView> find(UUID taskId) {
        return jdbc.query("SELECT id, request_id, execution_id, case_id, status, current_stage, error, created_at, updated_at FROM app.tasks WHERE id = ?",
                this::map, taskId).stream().findFirst();
    }

    @Transactional
    public TaskView retry(UUID taskId) {
        UUID executionId = UUID.randomUUID();
        int updated = jdbc.update("UPDATE app.tasks SET execution_id = ?, status = 'queued', current_stage = 'retry_requested', error = NULL, updated_at = now() WHERE id = ? AND status IN ('failed', 'timed_out', 'rejected')",
                executionId, taskId);
        if (updated == 0) {
            throw new IllegalStateException("task is not retryable or does not exist");
        }
        jdbc.update("INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json) VALUES (?, ?, 'execution.requested', ?::jsonb)",
                taskId, executionId, "{\"taskId\":\"" + taskId + "\",\"executionId\":\"" + executionId + "\"}");
        return find(taskId).orElseThrow();
    }

    private TaskView map(ResultSet rs, int ignored) throws SQLException {
        return new TaskView(rs.getObject("id", UUID.class), rs.getObject("request_id", UUID.class), rs.getObject("execution_id", UUID.class),
                rs.getString("case_id"), rs.getString("status"), rs.getString("current_stage"), null, rs.getString("error"),
                rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class));
    }

    private String toJson(Map<String, Object> metadata) {
        if (metadata == null || metadata.isEmpty()) return "{}";
        return "{\"keys\":" + metadata.size() + "}";
    }
}
