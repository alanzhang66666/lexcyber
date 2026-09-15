package com.lexcyber.server.review;

import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReviewService {
    private static final String OWNED_FROM = """
            FROM app.review_records r
            JOIN app.tasks t ON t.id = r.task_id
            JOIN app.cases c ON c.id = t.case_id AND c.owner_account_id = ?
            """;
    private static final String OWNED_SELECT = """
            SELECT r.id, r.task_id, t.case_id, r.result_version, r.status, r.decision,
                   r.actor, r.authenticated, r.comment, r.decided_at, r.created_at
            """ + OWNED_FROM;

    private final JdbcTemplate jdbc;

    public ReviewService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, int page, int size) {
        requireOwner(ownerAccountId);
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid page");
        }
        boolean filterStatus = status != null && !status.isBlank();
        List<Object> params = new ArrayList<>();
        params.add(ownerAccountId);
        String statusClause = "";
        if (filterStatus) {
            statusClause = " WHERE r.status = ?";
            params.add(status);
        }
        params.add(size);
        params.add(page * size);
        List<Map<String, Object>> items = jdbc.query(
                OWNED_SELECT + statusClause + " ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                this::map,
                params.toArray());
        List<Object> countParams = new ArrayList<>();
        countParams.add(ownerAccountId);
        if (filterStatus) {
            countParams.add(status);
        }
        Long total = jdbc.queryForObject(
                "SELECT COUNT(*) " + OWNED_FROM + statusClause,
                Long.class,
                countParams.toArray());
        return Map.of("items", items, "page", page, "size", size, "total", total == null ? 0L : total);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> get(UUID ownerAccountId, UUID reviewId) {
        return requireOwned(ownerAccountId, reviewId);
    }

    @Transactional
    public Map<String, Object> decide(UUID ownerAccountId, UUID reviewId, String decision, int resultVersion,
                                      String actor, String comment) {
        requireOwned(ownerAccountId, reviewId);
        String nextStatus = "approve".equals(decision) ? "approved" : "rejected";
        List<UUID> tasks = jdbc.query("""
                UPDATE app.review_records SET status=?, decision=?, actor=?, authenticated=true, comment=?, decided_at=now()
                WHERE id=? AND result_version=? AND status='pending'
                RETURNING task_id
                """, (rs, ignored) -> rs.getObject("task_id", UUID.class), nextStatus, decision, actor, comment, reviewId, resultVersion);
        if (tasks.isEmpty()) {
            requireOwned(ownerAccountId, reviewId);
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
        return requireOwned(ownerAccountId, reviewId);
    }

    private Map<String, Object> requireOwned(UUID ownerAccountId, UUID reviewId) {
        requireOwner(ownerAccountId);
        List<Map<String, Object>> rows = jdbc.query(OWNED_SELECT + " WHERE r.id = ?", this::map, ownerAccountId, reviewId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "REVIEW_NOT_FOUND", "复核记录不存在或不可访问");
        }
        return rows.get(0);
    }

    private static void requireOwner(UUID ownerAccountId) {
        if (ownerAccountId == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "session required");
        }
    }

    private Map<String, Object> map(ResultSet rs, int ignored) throws SQLException {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", rs.getObject("id", UUID.class));
        result.put("taskId", rs.getObject("task_id", UUID.class));
        String caseId = rs.getString("case_id");
        result.put("caseId", caseId == null || caseId.isBlank() ? null : caseId);
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
