package com.lexcyber.server.engine;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Applies callback and reconciliation results idempotently at the app boundary. */
@Service
public class EngineResultService {
    private final JdbcTemplate jdbc;

    public EngineResultService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
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

        if (payload.contentJson() != null) {
            if (payload.resultId() == null || payload.resultVersion() < 1 || payload.contentHash() == null
                    || !constantTimeHash(payload.contentJson(), payload.contentHash())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "result content hash mismatch");
            }
            jdbc.update("""
                    INSERT INTO app.result_versions(result_id, task_id, execution_id, version, result_type, content_json, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?::jsonb, ?)
                    ON CONFLICT (task_id, version) DO NOTHING
                    """, payload.resultId(), taskId, payload.executionId(), payload.resultVersion(), payload.resultType(), payload.contentJson(), payload.contentHash());
            Map<String, Object> stored = jdbc.queryForMap("SELECT result_id, content_hash FROM app.result_versions WHERE task_id=? AND version=?",
                    taskId, payload.resultVersion());
            if (!payload.resultId().equals(stored.get("result_id")) || !payload.contentHash().equals(stored.get("content_hash"))) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "result version already contains different content");
            }
        }

        if (current) {
            jdbc.update("UPDATE app.tasks SET status=?, current_stage=?, error_code=?, error=?, updated_at=now() WHERE id=? AND execution_id=?",
                    payload.status(), payload.currentStage(), payload.errorCode(), payload.errorMessage(), taskId, payload.executionId());
            if ("waiting_review".equals(payload.status()) && payload.resultVersion() >= 1) {
                jdbc.update("""
                        INSERT INTO app.review_records(id, task_id, result_version, status, decision)
                        VALUES (?, ?, ?, 'pending', 'none')
                        ON CONFLICT (task_id, result_version) DO NOTHING
                        """, UUID.randomUUID(), taskId, payload.resultVersion());
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
