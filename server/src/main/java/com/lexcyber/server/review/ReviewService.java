package com.lexcyber.server.review;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.DocumentPolicies;
import com.lexcyber.server.domain.ModulePolicies;
import java.nio.charset.StandardCharsets;
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
            LEFT JOIN app.tasks t ON t.id = r.task_id
            LEFT JOIN app.case_drafts d ON d.id = r.draft_id
            JOIN app.cases c ON c.owner_account_id = ?
              AND c.id = COALESCE(NULLIF(t.case_id, ''), d.case_id, r.case_id)
            """;
    private static final String MODULE_SQL = """
            COALESCE(NULLIF(t.metadata_json->>'module', ''),
              r.module_state,
              CASE WHEN r.draft_id IS NOT NULL THEN 'draft' END,
              CASE t.metadata_json->>'taskType'
                WHEN 'document.parse' THEN 'parse'
                WHEN 'sentencing.calculate' THEN 'sentencing'
                WHEN 'compliance.analyze' THEN 'compliance'
                WHEN 'conviction.analyze' THEN 'conviction'
                ELSE CASE WHEN t.id IS NOT NULL THEN 'task' END
              END)
            """;
    private static final String OWNED_SELECT = """
            SELECT r.id, r.task_id, COALESCE(NULLIF(t.case_id, ''), d.case_id, r.case_id) AS case_id,
                   r.result_version, r.status, r.decision,
                   r.actor, r.authenticated, r.comment, r.decided_at, r.created_at,
                   r.draft_id, r.draft_version, r.module_state, r.module_version,
                   r.archive_status, r.return_target,
                   """ + MODULE_SQL + " AS module " + OWNED_FROM;

    private final JdbcTemplate jdbc;
    private final CaseService cases;

    public ReviewService(JdbcTemplate jdbc, CaseService cases) {
        this.jdbc = jdbc;
        this.cases = cases;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, int page, int size) {
        return list(ownerAccountId, status, null, null, page, size);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, String module, int page, int size) {
        return list(ownerAccountId, status, module, null, page, size);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, String module, String archiveStatus,
                                    int page, int size) {
        requireOwner(ownerAccountId);
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid page");
        }
        boolean filterStatus = status != null && !status.isBlank();
        boolean filterModule = module != null && !module.isBlank();
        boolean filterArchive = archiveStatus != null && !archiveStatus.isBlank();
        if (filterArchive && !"open".equals(archiveStatus) && !"archived".equals(archiveStatus)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "archiveStatus must be open or archived");
        }
        List<Object> params = new ArrayList<>();
        params.add(ownerAccountId);
        StringBuilder where = new StringBuilder();
        if (filterStatus) {
            where.append(where.isEmpty() ? " WHERE " : " AND ").append("r.status = ?");
            params.add(status);
        }
        if (filterModule) {
            where.append(where.isEmpty() ? " WHERE " : " AND ").append(MODULE_SQL).append(" = ?");
            params.add(module);
        }
        if (filterArchive) {
            where.append(where.isEmpty() ? " WHERE " : " AND ").append("r.archive_status = ?");
            params.add(archiveStatus);
        }
        String filterClause = where.toString();
        params.add(size);
        params.add(page * size);
        List<Map<String, Object>> items = jdbc.query(
                OWNED_SELECT + filterClause + " ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                this::map,
                params.toArray());
        List<Object> countParams = new ArrayList<>();
        countParams.add(ownerAccountId);
        if (filterStatus) {
            countParams.add(status);
        }
        if (filterModule) {
            countParams.add(module);
        }
        if (filterArchive) {
            countParams.add(archiveStatus);
        }
        Long total = jdbc.queryForObject(
                "SELECT COUNT(*) " + OWNED_FROM + filterClause,
                Long.class,
                countParams.toArray());
        return Map.of("items", items, "page", page, "size", size, "total", total == null ? 0L : total);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> get(UUID ownerAccountId, UUID reviewId) {
        return requireOwned(ownerAccountId, reviewId);
    }

    @Transactional
    public Map<String, Object> open(UUID ownerAccountId, String caseId, ReviewOpen request) {
        return open(ownerAccountId, caseId, request, null);
    }

    @Transactional
    public Map<String, Object> open(UUID ownerAccountId, String caseId, ReviewOpen request, String idempotencyKey) {
        cases.lockOwned(ownerAccountId, caseId);
        String module = ModulePolicies.requireReviewModule(request.module());
        UUID taskId = request.taskId();
        String draftId = blankToNull(request.draftId());
        String moduleState = blankToNull(request.moduleState());
        if (taskId == null && draftId == null && moduleState == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                    "review needs taskId, draftId, or moduleState");
        }
        String key = normalizeIdempotencyKey(idempotencyKey);
        String requestHash = key == null ? null : reviewRequestHash(request);
        if (key != null) {
            Map<String, Object> replay = claimReviewIdempotency(ownerAccountId, caseId, key, requestHash);
            if (replay != null) return replay;
        }

        Integer draftVersion = request.draftVersion();
        Integer moduleVersion = request.moduleVersion();
        Integer resultVersion = request.resultVersion();

        if (draftId != null) {
            List<Integer> versions = jdbc.query(
                    "SELECT version FROM app.case_drafts WHERE id = ? AND case_id = ?",
                    (rs, ignored) -> rs.getInt(1), draftId, caseId);
            if (versions.isEmpty()) {
                throw new ApiException(HttpStatus.NOT_FOUND, "DRAFT_NOT_FOUND", "草稿不存在或不可访问");
            }
            int current = versions.get(0);
            if (draftVersion == null) {
                draftVersion = current;
            } else if (draftVersion != current) {
                throw new ApiException(HttpStatus.CONFLICT, "DRAFT_VERSION_CONFLICT", "草稿版本已变更");
            }
            if (resultVersion == null) {
                resultVersion = draftVersion;
            }
        }

        if (moduleState != null) {
            moduleState = ModulePolicies.requireModule(moduleState);
            List<Integer> versions = jdbc.query(
                    "SELECT version FROM app.case_module_states WHERE case_id = ? AND module = ?",
                    (rs, ignored) -> rs.getInt(1), caseId, moduleState);
            if (versions.isEmpty()) {
                throw new ApiException(HttpStatus.NOT_FOUND, "MODULE_NOT_FOUND", "模块空壳不存在");
            }
            int current = versions.get(0);
            if (moduleVersion == null) {
                moduleVersion = current;
            } else if (moduleVersion != current) {
                throw new ApiException(HttpStatus.CONFLICT, "MODULE_VERSION_CONFLICT", "模块版本已变更");
            }
            if (resultVersion == null) {
                resultVersion = Math.max(moduleVersion, 1);
            }
        }

        if (taskId != null) {
            List<Map<String, Object>> tasks = jdbc.query("""
                    SELECT case_id, (
                      SELECT COALESCE(MAX(version), 0) FROM app.result_versions rv WHERE rv.task_id = t.id
                    ) AS result_version
                    FROM app.tasks t WHERE t.id = ?
                    """, (rs, ignored) -> {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("caseId", rs.getString("case_id"));
                row.put("resultVersion", rs.getInt("result_version"));
                return row;
            }, taskId);
            if (tasks.isEmpty()) {
                throw new ApiException(HttpStatus.NOT_FOUND, "TASK_NOT_FOUND", "任务不存在或不可访问");
            }
            String taskCaseId = String.valueOf(tasks.get(0).get("caseId"));
            if (taskCaseId.isBlank() || !caseId.equals(taskCaseId)) {
                throw new ApiException(HttpStatus.NOT_FOUND, "TASK_NOT_FOUND", "任务不存在或不可访问");
            }
            int current = (Integer) tasks.get(0).get("resultVersion");
            if (current < 1) {
                throw new ApiException(HttpStatus.CONFLICT, "RESULT_VERSION_CONFLICT", "任务尚无结果版本");
            }
            if (resultVersion == null) {
                resultVersion = current;
            } else if (resultVersion != current) {
                throw new ApiException(HttpStatus.CONFLICT, "RESULT_VERSION_CONFLICT", "结果版本已变更");
            }
        }

        if (resultVersion == null || resultVersion < 1) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "resultVersion is required");
        }

        UUID reviewId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.review_records(
                    id, task_id, result_version, status, decision, case_id, draft_id, draft_version,
                    module_state, module_version, archive_status, return_target)
                VALUES (?, ?, ?, 'pending', 'none', ?, ?, ?, ?, ?, 'open', ?)
                """, reviewId, taskId, resultVersion, caseId, draftId, draftVersion,
                moduleState, moduleVersion, blankToNull(request.returnTarget()));
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES (?, 'review.open', 'review', ?, jsonb_build_object('caseId', ?, 'module', ?, 'resultVersion', ?))
                """, "account:" + ownerAccountId, reviewId.toString(), caseId, module, resultVersion);
        if (key != null) {
            jdbc.update("""
                    UPDATE app.review_open_idempotency SET review_id = ?
                    WHERE account_id = ? AND case_id = ? AND idempotency_key = ? AND request_hash = ?
                    """, reviewId, ownerAccountId, caseId, key, requestHash);
        }
        return requireOwned(ownerAccountId, reviewId);
    }

    @Transactional
    public Map<String, Object> archive(UUID ownerAccountId, UUID reviewId) {
        requireOwned(ownerAccountId, reviewId);
        int changed = jdbc.update("""
                UPDATE app.review_records SET archive_status = 'archived'
                WHERE id = ?
                """, reviewId);
        if (changed == 0) {
            throw new ApiException(HttpStatus.NOT_FOUND, "REVIEW_NOT_FOUND", "复核记录不存在或不可访问");
        }
        return requireOwned(ownerAccountId, reviewId);
    }

    @Transactional
    public Map<String, Object> decide(UUID ownerAccountId, UUID reviewId, String decision, int resultVersion,
                                      String actor, String comment) {
        Map<String, Object> current = requireOwned(ownerAccountId, reviewId);
        requireLiveTarget(current);
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
        jdbc.update("INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json) VALUES (?, ?, 'review', ?, ?::jsonb)",
                actor, decision, reviewId.toString(), "{\"resultVersion\":" + resultVersion + "}");
        if (taskId != null) {
            Map<String, Object> task = jdbc.queryForMap("SELECT request_id, execution_id FROM app.tasks WHERE id=?", taskId);
            UUID requestId = (UUID) task.get("request_id");
            UUID executionId = (UUID) task.get("execution_id");
            jdbc.update("UPDATE app.tasks SET status=?, current_stage='human_review_decision', updated_at=now() WHERE id=? AND status='waiting_review'",
                    nextStatus.equals("approved") ? "completed" : "rejected", taskId);
            jdbc.update("""
                    INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                    VALUES (?, ?, 'review', ?, jsonb_build_object('taskId', ?::text, 'requestId', ?::text,
                                                                   'executionId', ?::text, 'resultVersion', ?))
                    """, actor, decision, reviewId.toString(), taskId.toString(), requestId.toString(), executionId.toString(), resultVersion);
        }
        return requireOwned(ownerAccountId, reviewId);
    }

    private Map<String, Object> claimReviewIdempotency(UUID ownerAccountId, String caseId,
                                                        String key, String requestHash) {
        jdbc.update("""
                INSERT INTO app.review_open_idempotency(
                    account_id, case_id, idempotency_key, request_hash, review_id)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT (account_id, case_id, idempotency_key) DO NOTHING
                """, ownerAccountId, caseId, key, requestHash);
        Map<String, Object> row = jdbc.queryForMap("""
                SELECT request_hash, review_id
                FROM app.review_open_idempotency
                WHERE account_id = ? AND case_id = ? AND idempotency_key = ?
                FOR UPDATE
                """, ownerAccountId, caseId, key);
        if (!requestHash.equals(String.valueOf(row.get("request_hash")))) {
            throw new ApiException(HttpStatus.CONFLICT, "IDEMPOTENCY_CONFLICT",
                    "相同幂等键已用于不同复核内容");
        }
        Object reviewId = row.get("review_id");
        if (reviewId == null) return null;
        UUID resolved = reviewId instanceof UUID uuid ? uuid : UUID.fromString(String.valueOf(reviewId));
        return requireOwned(ownerAccountId, resolved);
    }

    private static String reviewRequestHash(ReviewOpen request) {
        StringBuilder canonical = new StringBuilder();
        appendHashPart(canonical, request.module());
        appendHashPart(canonical, request.draftId());
        appendHashPart(canonical, request.draftVersion());
        appendHashPart(canonical, request.moduleState());
        appendHashPart(canonical, request.moduleVersion());
        appendHashPart(canonical, request.resultVersion());
        appendHashPart(canonical, request.taskId());
        appendHashPart(canonical, request.returnTarget());
        return DocumentPolicies.sha256Hex(canonical.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static void appendHashPart(StringBuilder target, Object value) {
        String part = value == null ? "" : String.valueOf(value);
        target.append(part.length()).append(':').append(part).append(';');
    }

    private static String normalizeIdempotencyKey(String value) {
        if (value == null || value.isBlank()) return null;
        String key = value.trim();
        if (key.length() > 128) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "Idempotency-Key is too long");
        }
        return key;
    }

    private void requireLiveTarget(Map<String, Object> current) {
        String draftId = (String) current.get("draftId");
        Integer draftVersion = (Integer) current.get("draftVersion");
        if (draftId != null) {
            List<Integer> versions = jdbc.query(
                    "SELECT version FROM app.case_drafts WHERE id = ?",
                    (rs, ignored) -> rs.getInt(1), draftId);
            if (versions.isEmpty() || draftVersion == null || draftVersion != versions.get(0)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "review is already decided or has a different result version");
            }
        }
        String moduleState = (String) current.get("moduleState");
        Integer moduleVersion = (Integer) current.get("moduleVersion");
        String caseId = (String) current.get("caseId");
        if (moduleState != null) {
            List<Integer> versions = jdbc.query(
                    "SELECT version FROM app.case_module_states WHERE case_id = ? AND module = ?",
                    (rs, ignored) -> rs.getInt(1), caseId, moduleState);
            if (versions.isEmpty() || moduleVersion == null || moduleVersion != versions.get(0)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "review is already decided or has a different result version");
            }
        }
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
        result.put("module", rs.getString("module"));
        result.put("draftId", rs.getString("draft_id"));
        Integer draftVersion = (Integer) rs.getObject("draft_version");
        result.put("draftVersion", draftVersion);
        result.put("moduleState", rs.getString("module_state"));
        Integer moduleVersion = (Integer) rs.getObject("module_version");
        result.put("moduleVersion", moduleVersion);
        String archive = rs.getString("archive_status");
        result.put("archiveStatus", archive == null || archive.isBlank() ? "open" : archive);
        result.put("returnTarget", rs.getString("return_target"));
        return result;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
