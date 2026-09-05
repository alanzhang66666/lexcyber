package com.lexcyber.server.review;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReviewService {
    private final JdbcTemplate jdbc;

    public ReviewService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(String status, int page, int size) {
        if (page < 0 || size < 1 || size > 100) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid page");
        String filter = status == null || status.isBlank() ? "" : " WHERE r.status = ?";
        Object[] params = filter.isEmpty() ? new Object[] {size, page * size} : new Object[] {status, size, page * size};
        List<Map<String, Object>> items = jdbc.query("SELECT r.id, r.task_id, r.result_version, r.status, r.decision, r.actor, r.authenticated, r.comment, r.decided_at, r.created_at FROM app.review_records r" + filter + " ORDER BY r.created_at DESC LIMIT ? OFFSET ?", this::map, params);
        Long total = filter.isEmpty() ? jdbc.queryForObject("SELECT COUNT(*) FROM app.review_records", Long.class) : jdbc.queryForObject("SELECT COUNT(*) FROM app.review_records WHERE status = ?", Long.class, status);
        return Map.of("items", items, "page", page, "size", size, "total", total == null ? 0L : total);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> get(UUID reviewId) {
        List<Map<String, Object>> rows = jdbc.query("SELECT r.id, r.task_id, r.result_version, r.status, r.decision, r.actor, r.authenticated, r.comment, r.decided_at, r.created_at FROM app.review_records r WHERE r.id = ?", this::map, reviewId);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "review not found");
        return rows.get(0);
    }

    @Transactional
    public Map<String, Object> decide(UUID reviewId, String decision, int resultVersion, String actor, String comment) {
        String nextStatus = "approve".equals(decision) ? "approved" : "rejected";
        List<UUID> tasks = jdbc.query("""
                UPDATE app.review_records SET status=?, decision=?, actor=?, authenticated=true, comment=?, decided_at=now()
                WHERE id=? AND result_version=? AND status='pending'
                RETURNING task_id
                """, (rs, ignored) -> rs.getObject("task_id", UUID.class), nextStatus, decision, actor, comment, reviewId, resultVersion);
        if (tasks.isEmpty()) {
            List<String> states = jdbc.query("SELECT status FROM app.review_records WHERE id=?", (rs, ignored) -> rs.getString("status"), reviewId);
            if (states.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "review not found");
            throw new ResponseStatusException(HttpStatus.CONFLICT, "review is already decided or has a different result version");
        }
        UUID taskId = tasks.get(0);
        Map<String, Object> task = jdbc.queryForMap("SELECT request_id, execution_id FROM app.tasks WHERE id=?", taskId);
        UUID requestId = (UUID) task.get("request_id");
        UUID executionId = (UUID) task.get("execution_id");
        jdbc.update("UPDATE app.tasks SET status=?, current_stage='human_review_decision', updated_at=now() WHERE id=? AND status='waiting_review'", nextStatus.equals("approved") ? "completed" : "rejected", taskId);
        jdbc.update("INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json) VALUES (?, ?, 'review', ?, ?::jsonb)",
                actor, decision, reviewId.toString(), "{\"resultVersion\":" + resultVersion + "}");
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES (?, ?, 'review', ?, jsonb_build_object('taskId', ?::text, 'requestId', ?::text,
                                                               'executionId', ?::text, 'resultVersion', ?))
                """, actor, decision, reviewId.toString(), taskId.toString(), requestId.toString(), executionId.toString(), resultVersion);
        return get(reviewId);
    }

    private Map<String, Object> map(ResultSet rs, int ignored) throws SQLException {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", rs.getObject("id", UUID.class));
        result.put("taskId", rs.getObject("task_id", UUID.class));
        result.put("resultVersion", rs.getInt("result_version"));
        result.put("status", rs.getString("status"));
        result.put("decision", rs.getString("decision"));
        result.put("actor", rs.getString("actor"));
        result.put("authenticated", rs.getBoolean("authenticated"));
        result.put("comment", rs.getString("comment"));
        result.put("decidedAt", rs.getObject("decided_at"));
        result.put("createdAt", rs.getObject("created_at"));
        return result;
    }
}
