package com.lexcyber.server.review;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.DocumentPolicies;
import com.lexcyber.server.domain.DraftApprovalService;
import com.lexcyber.server.domain.IdempotencyService;
import com.lexcyber.server.domain.IdentityService;
import com.lexcyber.server.domain.ModuleConfirmationService;
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

/**
 * /v1 复核端点适配层：权威绑定为 artifact_version_id（INV-REVIEW-REF-001）。
 * taskId/draftId/moduleState 旧请求字段在 open 时解析为具体 artifact_version；
 * ReviewTargetView 字段（draftId/moduleState/returnTarget…）由 stream scope_key 反算，不持久化（INV-REVIEW-003）。
 */
@Service
public class ReviewService {
    private static final String OWNED_FROM = """
            FROM app.review_records r
            JOIN app.artifact_version v ON v.artifact_version_id = r.artifact_version_id
            JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
            LEFT JOIN app.draft_head dh ON dh.artifact_stream_id = s.artifact_stream_id
            JOIN app.cases c ON c.owner_account_id = ? AND c.id = r.case_id
            """;
    private static final String OWNED_SELECT = """
            SELECT r.review_id AS id, r.artifact_version_id, r.case_id,
                   v.version AS result_version, r.status, r.decision,
                   r.actor_id, r.comment, r.decided_at, r.created_at,
                   s.kind AS module, s.scope_key, dh.draft_id AS head_draft_id
            """ + OWNED_FROM;

    private final JdbcTemplate jdbc;
    private final CaseService cases;
    private final IdentityService ids;
    private final IdempotencyService idempotency;
    private final ModuleConfirmationService moduleConfirmation;
    private final DraftApprovalService draftApproval;

    public ReviewService(JdbcTemplate jdbc, CaseService cases, IdempotencyService idempotency,
                         ModuleConfirmationService moduleConfirmation,
                         DraftApprovalService draftApproval) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.ids = new IdentityService(jdbc);
        this.idempotency = idempotency;
        this.moduleConfirmation = moduleConfirmation;
        this.draftApproval = draftApproval;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, int page, int size) {
        return list(ownerAccountId, status, null, null, page, size);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, String module, int page, int size) {
        return list(ownerAccountId, status, module, null, page, size);
    }

    /** archiveStatus 参数已弃用（归档改案件级）：忽略并在控制器层加 Deprecation 头。 */
    @Transactional(readOnly = true)
    public Map<String, Object> list(UUID ownerAccountId, String status, String module, String archiveStatus,
                                    int page, int size) {
        requireOwner(ownerAccountId);
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid page");
        }
        boolean filterStatus = status != null && !status.isBlank();
        boolean filterModule = module != null && !module.isBlank();
        List<Object> params = new ArrayList<>();
        params.add(ownerAccountId);
        StringBuilder where = new StringBuilder();
        if (filterStatus) {
            where.append(where.isEmpty() ? " WHERE " : " AND ").append("r.status = ?");
            params.add(status);
        }
        if (filterModule) {
            where.append(where.isEmpty() ? " WHERE " : " AND ").append("s.kind = ?");
            params.add(module);
        }
        String filterClause = where.toString();
        params.add(size);
        params.add(page * size);
        List<Map<String, Object>> items = jdbc.query(
                OWNED_SELECT + filterClause + " ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                this::map, params.toArray());
        List<Object> countParams = new ArrayList<>();
        countParams.add(ownerAccountId);
        if (filterStatus) {
            countParams.add(status);
        }
        if (filterModule) {
            countParams.add(module);
        }
        Long total = jdbc.queryForObject(
                "SELECT COUNT(*) " + OWNED_FROM + filterClause,
                Long.class, countParams.toArray());
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
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        String module = ModulePolicies.requireReviewModule(request.module());
        UUID taskId = request.taskId();
        String draftId = blankToNull(request.draftId());
        if (draftId != null) {
            draftId = ids.draftId(draftId);
        }
        String moduleState = blankToNull(request.moduleState());
        if (taskId == null && draftId == null && moduleState == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                    "review needs taskId, draftId, or moduleState");
        }
        String key = normalizeIdempotencyKey(idempotencyKey);
        if (key != null) {
            IdempotencyService.Claim claim = idempotency.claim(
                    ownerAccountId, key, reviewRequestHash(request));
            if (claim.replay()) {
                return requireOwned(ownerAccountId, claim.resourceId());
            }
        }

        UUID artifactVersionId = resolveArtifact(caseId, request, taskId, draftId, moduleState);
        UUID reviewId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.review_records(review_id, artifact_version_id, case_id, status, actor_id)
                VALUES (?, ?, ?::uuid, 'pending', ?)
                """, reviewId, artifactVersionId, caseId, ownerAccountId);
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES (?, 'review.open', 'review', ?, jsonb_build_object('caseId', ?, 'module', ?))
                """, "account:" + ownerAccountId, reviewId.toString(), caseId, module);
        if (key != null) {
            idempotency.record(ownerAccountId, key, "review", reviewId, 201);
        }
        return requireOwned(ownerAccountId, reviewId);
    }

    /** 把 /v1 的三类目标解析为具体 artifact_version_id。 */
    private UUID resolveArtifact(String caseId, ReviewOpen request,
                                 UUID taskId, String draftId, String moduleState) {
        if (taskId != null) {
            List<Map<String, Object>> versions = jdbc.queryForList("""
                    SELECT v.artifact_version_id, v.version
                    FROM app.artifact_version v
                    JOIN app.tasks t ON t.execution_id = v.execution_id
                    JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                    WHERE t.id = ? AND s.case_id = ?::uuid
                    ORDER BY v.version DESC
                    """, taskId, caseId);
            if (versions.isEmpty()) {
                throw new ApiException(HttpStatus.CONFLICT, "RESULT_VERSION_CONFLICT", "任务尚无已发布结果");
            }
            Integer wanted = request.resultVersion();
            for (Map<String, Object> row : versions) {
                if (wanted == null || wanted.equals(((Number) row.get("version")).intValue())) {
                    return (UUID) row.get("artifact_version_id");
                }
            }
            throw new ApiException(HttpStatus.CONFLICT, "RESULT_VERSION_CONFLICT", "结果版本已变更");
        }
        if (draftId != null) {
            return resolveStreamVersion(caseId, "draft", "draft:" + draftId,
                    request.draftVersion(), "DRAFT_NOT_FOUND", "DRAFT_VERSION_CONFLICT");
        }
        String module = ModulePolicies.requireModule(moduleState);
        return resolveStreamVersion(caseId, module, "module:" + module,
                request.moduleVersion(), "MODULE_NOT_FOUND", "MODULE_VERSION_CONFLICT");
    }

    private UUID resolveStreamVersion(String caseId, String kind, String scopeKey, Integer wanted,
                                      String notFoundCode, String conflictCode) {
        List<Map<String, Object>> versions = jdbc.queryForList("""
                SELECT v.artifact_version_id, v.version, v.artifact_version_id = s.latest_version_id AS is_latest
                FROM app.artifact_stream s
                JOIN app.artifact_version v ON v.artifact_stream_id = s.artifact_stream_id
                WHERE s.case_id = ?::uuid AND s.kind = ? AND s.scope_key = ?
                ORDER BY v.version DESC
                """, caseId, kind, scopeKey);
        if (versions.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, notFoundCode, "目标不存在或尚无工件版本");
        }
        for (Map<String, Object> row : versions) {
            if (wanted == null || wanted.equals(((Number) row.get("version")).intValue())) {
                return (UUID) row.get("artifact_version_id");
            }
        }
        throw new ApiException(HttpStatus.CONFLICT, conflictCode, "版本已变更");
    }

    /** /v1 的 archive 端点已移除：归档改在案件级（POST /v2/cases/{id}/archives）。 */
    @Transactional
    public Map<String, Object> archive(UUID ownerAccountId, UUID reviewId) {
        throw new ApiException(HttpStatus.GONE, "REVIEW_ARCHIVE_REMOVED",
                "复核归档已移除；归档为案件级操作，请使用 POST /v2/cases/{caseId}/archives");
    }

    @Transactional
    public Map<String, Object> decide(UUID ownerAccountId, UUID reviewId, String decision, int resultVersion,
                                      String actor, String comment) {
        Map<String, Object> current = requireOwned(ownerAccountId, reviewId);
        String caseId = (String) current.get("caseId");
        cases.lockOwned(ownerAccountId, caseId);
        String nextStatus = "approve".equals(decision) ? "approved" : "rejected";
        UUID artifactVersionId = (UUID) current.get("artifactVersionId");
        Number currentVersion = (Number) current.get("resultVersion");
        if (currentVersion == null || currentVersion.intValue() != resultVersion) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "RESULT_VERSION_CONFLICT");
        }
        // 锁序 stream → review（与 publish 的 stream→review 同序防互等死锁）：
        // SHARE 期间 stream.latest 不会变，下面的 live 检查在该锁内稳定成立。
        List<Map<String, Object>> streamLock = jdbc.queryForList("""
                SELECT s.artifact_stream_id FROM app.artifact_stream s
                JOIN app.artifact_version v ON v.artifact_stream_id = s.artifact_stream_id
                WHERE v.artifact_version_id = ? FOR SHARE OF s
                """, artifactVersionId);
        if (streamLock.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "artifact version not found");
        }
        // 复核只针对仍存活（latest）的版本做决定；被新版本替代的复核已由发布路径置 superseded
        Long live = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                WHERE v.artifact_version_id = ? AND s.latest_version_id = v.artifact_version_id
                """, Long.class, artifactVersionId);
        if (live == null || live == 0L) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "review is already decided or has a different result version");
        }
        List<UUID> decided = jdbc.query("""
                UPDATE app.review_records
                SET status = ?, decision = ?, actor_id = ?, comment = ?, decided_at = now()
                WHERE review_id = ? AND status = 'pending'
                RETURNING review_id
                """, (rs, ignored) -> rs.getObject(1, UUID.class),
                nextStatus, decision, ownerAccountId, comment, reviewId);
        if (decided.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "review is already decided or has a different result version");
        }
        jdbc.update("INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json) VALUES (?, ?, 'review', ?, ?::jsonb)",
                actor, decision, reviewId.toString(), "{\"resultVersion\":" + resultVersion + "}");
        if ("approved".equals(nextStatus)) {
            String module = (String) current.get("module");
            if ("draft".equals(module)) {
                UUID draftId = draftIdForVersion(caseId, artifactVersionId);
                draftApproval.approve(caseId, draftId, ownerAccountId);
            } else if (ModulePolicies.MODULES.contains(module)) {
                moduleConfirmation.confirm(caseId, module, ownerAccountId);
            }
        }
        return requireOwned(ownerAccountId, reviewId);
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

    private Map<String, Object> requireOwned(UUID ownerAccountId, UUID reviewId) {
        requireOwner(ownerAccountId);
        List<Map<String, Object>> rows = jdbc.query(OWNED_SELECT + " WHERE r.review_id = ?", this::map, ownerAccountId, reviewId);
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
        UUID artifactVersionId = rs.getObject("artifact_version_id", UUID.class);
        String caseId = rs.getString("case_id");
        String module = rs.getString("module");
        String scopeKey = rs.getString("scope_key");
        result.put("id", rs.getObject("id", UUID.class));
        result.put("artifactVersionId", artifactVersionId);
        result.put("taskId", taskFor(artifactVersionId));
        result.put("caseId", caseId);
        result.put("resultVersion", rs.getInt("result_version"));
        result.put("status", rs.getString("status"));
        result.put("decision", rs.getString("decision"));
        result.put("actor", actorName(rs.getObject("actor_id", UUID.class)));
        result.put("authenticated", rs.getObject("actor_id") != null);
        result.put("comment", rs.getString("comment"));
        result.put("decidedAt", rs.getObject("decided_at"));
        result.put("createdAt", rs.getObject("created_at"));
        result.put("module", module);
        result.put("archiveStatus", "open");
        // scope 反算展示字段（不持久化，INV-REVIEW-003）
        UUID headDraftId = rs.getObject("head_draft_id", UUID.class);
        if (headDraftId != null || (scopeKey != null && scopeKey.startsWith("draft:"))) {
            result.put("draftId", headDraftId == null
                    ? scopeKey.substring("draft:".length()) : headDraftId.toString());
            result.put("draftVersion", rs.getInt("result_version"));
            result.put("returnTarget", "/cases/" + caseId + "/drafts");
        } else {
            result.put("draftId", null);
            result.put("draftVersion", null);
            result.put("returnTarget", "/cases/" + caseId);
        }
        if (scopeKey != null && scopeKey.startsWith("module:")) {
            result.put("moduleState", scopeKey.substring("module:".length()));
            result.put("moduleVersion", rs.getInt("result_version"));
        } else {
            result.put("moduleState", null);
            result.put("moduleVersion", null);
        }
        return result;
    }

    private UUID draftIdForVersion(String caseId, UUID artifactVersionId) {
        List<UUID> drafts = jdbc.query("""
                SELECT h.draft_id
                FROM app.draft_head h
                JOIN app.artifact_version v ON v.artifact_stream_id = h.artifact_stream_id
                WHERE h.case_id = ?::uuid AND v.artifact_version_id = ?
                """, (rs, ignored) -> rs.getObject(1, UUID.class), caseId, artifactVersionId);
        if (drafts.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "draft head is not bound to the reviewed artifact version");
        }
        return drafts.get(0);
    }

    private UUID taskFor(UUID artifactVersionId) {
        List<UUID> tasks = jdbc.query("""
                SELECT t.id FROM app.tasks t
                JOIN app.artifact_version v ON v.execution_id = t.execution_id
                WHERE v.artifact_version_id = ?
                """, (rs, ignored) -> rs.getObject(1, UUID.class), artifactVersionId);
        return tasks.isEmpty() ? null : tasks.get(0);
    }

    private String actorName(UUID actorId) {
        if (actorId == null) {
            return null;
        }
        List<String> names = jdbc.query(
                "SELECT username FROM app.accounts WHERE id = ?",
                (rs, ignored) -> rs.getString(1), actorId);
        return names.isEmpty() ? null : names.get(0);
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
