package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.EngineCapabilitiesClient;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * /v2 生命周期端点的服务层（contracts/public-api-v2.yaml）。
 * 只暴露指针与工件视图，不复制正文（§11.1）；确认/批准判定走统一服务（INV-PIPE-003）。
 */
@Service
public class V2LifecycleService {
    private final JdbcTemplate jdbc;
    private final CaseService cases;
    private final IdentityService ids;
    private final FactsBaselineService baseline;
    private final ModuleConfirmationService moduleConfirmation;
    private final DraftApprovalService draftApproval;
    private final CaseArchiveService archives;
    private final EngineCapabilitiesClient capabilities;
    private final TaskService tasks;

    public V2LifecycleService(JdbcTemplate jdbc, CaseService cases, FactsBaselineService baseline,
                              ModuleConfirmationService moduleConfirmation,
                              DraftApprovalService draftApproval, CaseArchiveService archives,
                              EngineCapabilitiesClient capabilities, TaskService tasks) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.ids = new IdentityService(jdbc);
        this.baseline = baseline;
        this.moduleConfirmation = moduleConfirmation;
        this.draftApproval = draftApproval;
        this.archives = archives;
        this.capabilities = capabilities;
        this.tasks = tasks;
    }

    // ---------- facts ----------

    @Transactional
    public Map<String, Object> createFactsVersion(UUID ownerAccountId, String caseId) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        UUID versionId = baseline.createDraftVersion(caseId, ownerAccountId);
        return factsVersionView(versionId);
    }

    @Transactional
    public Map<String, Object> confirmFactsVersion(UUID ownerAccountId, String caseId,
            UUID factsVersionId, UUID expectedConfirmedId) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        baseline.confirm(caseId, factsVersionId, expectedConfirmedId, ownerAccountId);
        return factsHeadView(caseId);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listFactsVersions(UUID ownerAccountId, String caseId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return baseline.listVersions(caseId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> factsVersionDetail(UUID ownerAccountId, String caseId, UUID versionId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return baseline.versionDetail(caseId, versionId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> factsVersionDiff(UUID ownerAccountId, String caseId,
            UUID fromId, UUID toId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return baseline.diffVersions(caseId, fromId, toId);
    }

    @Transactional
    public Map<String, Object> cloneFactsVersion(UUID ownerAccountId, String caseId, UUID versionId) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        baseline.cloneIntoWorkingCopy(caseId, versionId);
        return baseline.editableEntities(caseId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> factsEntities(UUID ownerAccountId, String caseId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return baseline.editableEntities(caseId);
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> replaceFactsEntities(UUID ownerAccountId, String caseId,
            String kind, Map<String, Object> body) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        Object raw = body == null ? null : body.get("items");
        if (raw != null && !(raw instanceof List)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "items must be an array");
        }
        baseline.replaceEntities(caseId, kind, (List<Map<String, Object>>) raw);
        return baseline.editableEntities(caseId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> factsHead(UUID ownerAccountId, String caseId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return factsHeadView(caseId);
    }

    private Map<String, Object> factsVersionView(UUID versionId) {
        Map<String, Object> row = jdbc.queryForMap("""
                SELECT v.facts_version_id, v.case_id, v.version, v.content_hash, v.created_at,
                       v.confirmed_at, h.confirmed_facts_version_id
                FROM app.facts_version v
                LEFT JOIN app.facts_head h ON h.confirmed_facts_version_id = v.facts_version_id
                WHERE v.facts_version_id = ?
                """, versionId);
        String status = row.get("confirmed_at") == null ? "draft"
                : (versionId.equals(row.get("confirmed_facts_version_id")) ? "confirmed" : "superseded");
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("factsVersionId", versionId);
        view.put("caseId", row.get("case_id"));
        view.put("version", row.get("version"));
        view.put("status", status);
        view.put("contentHash", row.get("content_hash"));
        view.put("createdAt", row.get("created_at"));
        view.put("confirmedAt", row.get("confirmed_at"));
        return view;
    }

    private Map<String, Object> factsHeadView(String caseId) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT confirmed_facts_version_id, updated_at FROM app.facts_head WHERE case_id = ?::uuid",
                caseId);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("caseId", caseId);
        view.put("confirmedFactsVersionId",
                rows.isEmpty() ? null : rows.get(0).get("confirmed_facts_version_id"));
        view.put("updatedAt", rows.isEmpty() ? null : rows.get(0).get("updated_at"));
        return view;
    }

    // ---------- module head ----------

    @Transactional(readOnly = true)
    public Map<String, Object> moduleHead(UUID ownerAccountId, String caseId, String module) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        String resolved = module.trim();
        if (!List.of("compliance", "conviction", "sentencing").contains(resolved)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "unknown module");
        }
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT h.artifact_stream_id, h.confirmed_version_id, h.stale, h.stale_reason, h.updated_at,
                       s.latest_version_id
                FROM app.module_head h
                JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                WHERE h.case_id = ?::uuid AND h.module = ?
                """, caseId, resolved);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("caseId", caseId);
        view.put("module", resolved);
        if (rows.isEmpty()) {
            view.put("streamId", null);
            view.put("latestVersionId", null);
            view.put("confirmedVersionId", null);
            view.put("effectivelyConfirmed", false);
            view.put("stale", true);
            view.put("staleReason", null);
            view.put("updatedAt", null);
            return view;
        }
        Map<String, Object> r = rows.get(0);
        boolean effective = r.get("confirmed_version_id") != null
                && !Boolean.TRUE.equals(r.get("stale"));
        view.put("streamId", r.get("artifact_stream_id"));
        view.put("latestVersionId", r.get("latest_version_id"));
        view.put("confirmedVersionId", r.get("confirmed_version_id"));
        view.put("effectivelyConfirmed", effective);
        view.put("stale", r.get("stale"));
        view.put("staleReason", r.get("stale_reason"));
        view.put("updatedAt", r.get("updated_at"));
        return view;
    }

    // ---------- executions ----------

    /**
     * 模块执行门闩（INV-GATE-002）：先查 Engine 能力声明——所需 rule family
     * 全部存在 approved 规则包才可派发；能力缺失返回 MODULE_EXECUTION_UNAVAILABLE。
     * 能力具备 → 把 confirmed FactsVersion 快照嵌入执行 metadata
     * （INV-DATA-OWN-002：Engine 不跨 schema 读输入），经 createModuleTask 派发。
     */
    @Transactional
    public Map<String, Object> dispatchModuleExecution(UUID ownerAccountId, String caseId, String module) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        String taskType = switch (module) {
            case "compliance" -> TaskPolicies.COMPLIANCE_ANALYZE;
            case "conviction" -> TaskPolicies.CONVICTION_ANALYZE;
            case "sentencing" -> TaskPolicies.SENTENCING_CALCULATE;
            default -> throw new ApiException(HttpStatus.NOT_FOUND, "MODULE_NOT_FOUND", "未知模块");
        };
        if (!capabilities.moduleAvailable(module)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "MODULE_EXECUTION_UNAVAILABLE",
                    "模块执行能力未启用：Engine 无已会签规则包覆盖模块 " + module);
        }
        UUID factsVersionId = baseline.requireConfirmedVersionId(caseId);
        Object factsPayload = baseline.versionDetail(caseId, factsVersionId).get("payload");
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("taskType", taskType);
        metadata.put("module", module);
        metadata.put("factsVersionId", factsVersionId.toString());
        metadata.put("factsSnapshot", factsPayload);
        TaskView task = tasks.createModuleTask(
                new TaskCreate("module:" + module, caseId, null, metadata));
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("taskId", task.id());
        view.put("executionId", task.executionId());
        view.put("status", task.status());
        view.put("module", module);
        return view;
    }

    /**
     * 文书渲染派发：doc_type 必须有 approved 模板（能力门闩），confirmed facts
     * + 上游模块最新已发布 payload 一并嵌入 metadata（INV-DATA-OWN-002）。
     */
    @Transactional
    public Map<String, Object> dispatchDraftRender(UUID ownerAccountId, String caseId, String docType) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        if (docType == null || docType.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "DOC_TYPE_MISSING", "需要 docType");
        }
        if (!capabilities.templateAvailable(docType)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "DRAFT_RENDER_UNAVAILABLE",
                    "文书渲染能力未启用：doc_type " + docType + " 无已会签模板");
        }
        UUID factsVersionId = baseline.requireConfirmedVersionId(caseId);
        Object factsPayload = baseline.versionDetail(caseId, factsVersionId).get("payload");
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("taskType", TaskPolicies.DRAFT_RENDER);
        metadata.put("docType", docType);
        metadata.put("factsVersionId", factsVersionId.toString());
        metadata.put("factsSnapshot", factsPayload);
        metadata.put("artifacts", latestModulePayloads(caseId));
        TaskView task = tasks.createModuleTask(
                new TaskCreate("draft:" + docType, caseId, null, metadata));
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("taskId", task.id());
        view.put("executionId", task.executionId());
        view.put("status", task.status());
        view.put("docType", docType);
        return view;
    }

    /** 各模块流最新已发布版本 payload（渲染模板取上游结论用；无则空）。 */
    private Map<String, Object> latestModulePayloads(String caseId) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT DISTINCT ON (s.kind) s.kind, v.payload::text AS payload
                FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                WHERE s.case_id = ?::uuid AND s.kind IN ('compliance','conviction','sentencing')
                ORDER BY s.kind, v.version DESC
                """, caseId);
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map<String, Object> r : rows) {
            out.put(String.valueOf(r.get("kind")), parseJson(r.get("payload")));
        }
        return out;
    }

    /** 案件下全部 draft 流（draft:{docType}）及其最新工件版本指针，供渲染结果发现。 */
    @Transactional(readOnly = true)
    public Map<String, Object> listDraftStreams(UUID ownerAccountId, String caseId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT s.artifact_stream_id, s.scope_key, s.latest_version_id, s.updated_at
                FROM app.artifact_stream s
                WHERE s.case_id = ?::uuid AND s.kind = 'draft'
                ORDER BY s.scope_key
                """, caseId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("streamId", r.get("artifact_stream_id"));
            item.put("docType", String.valueOf(r.get("scope_key")).replaceFirst("^draft:", ""));
            item.put("latestVersionId", r.get("latest_version_id"));
            item.put("updatedAt", r.get("updated_at"));
            items.add(item);
        }
        return Map.of("items", items);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> execution(UUID ownerAccountId, UUID executionId) {
        requireOwner(ownerAccountId);
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT t.id, t.execution_id, t.case_id, t.status, t.created_at
                FROM app.tasks t
                LEFT JOIN app.cases c ON c.id = t.case_id
                WHERE t.execution_id = ? AND (c.owner_account_id = ? OR t.case_id IS NULL)
                """, executionId, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "EXECUTION_NOT_FOUND", "执行不存在或不可访问");
        }
        Map<String, Object> t = rows.get(0);
        String state = switch (String.valueOf(t.get("status"))) {
            case "queued" -> "queued";
            case "running" -> "running";
            case "completed", "waiting_review", "rejected" -> "completed";
            default -> "failed";
        };
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("executionId", t.get("execution_id"));
        view.put("taskId", t.get("id"));
        view.put("caseId", t.get("case_id"));
        view.put("state", state);
        view.put("createdAt", t.get("created_at"));
        return view;
    }

    // ---------- artifact versions ----------

    @Transactional(readOnly = true)
    public Map<String, Object> artifactVersion(UUID ownerAccountId, UUID artifactVersionId) {
        requireOwner(ownerAccountId);
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT v.artifact_version_id, v.artifact_stream_id, v.version, v.schema_version,
                       v.outcome_status, v.payload::text AS payload, v.blockers::text AS blockers,
                       v.dependency_snapshot::text AS dependency_snapshot, v.execution_id,
                       v.output_hash, v.created_at, s.case_id, s.kind, s.scope_key
                FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                JOIN app.cases c ON c.id = s.case_id
                WHERE v.artifact_version_id = ? AND c.owner_account_id = ?
                """, artifactVersionId, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "ARTIFACT_NOT_FOUND", "工件版本不存在或不可访问");
        }
        Map<String, Object> r = rows.get(0);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("artifactVersionId", r.get("artifact_version_id"));
        view.put("streamId", r.get("artifact_stream_id"));
        view.put("caseId", r.get("case_id"));
        view.put("kind", r.get("kind"));
        view.put("scopeKey", r.get("scope_key"));
        view.put("version", r.get("version"));
        view.put("schemaVersion", r.get("schema_version"));
        view.put("outcomeStatus", r.get("outcome_status"));
        view.put("payload", parseJson(r.get("payload")));
        view.put("blockers", parseJson(r.get("blockers")));
        view.put("dependencySnapshot", parseJson(r.get("dependency_snapshot")));
        view.put("executionId", r.get("execution_id"));
        view.put("outputHash", r.get("output_hash"));
        view.put("createdAt", r.get("created_at"));
        return view;
    }

    // ---------- reviews on artifact versions ----------

    @Transactional
    public Map<String, Object> openReview(UUID ownerAccountId, UUID artifactVersionId, String comment) {
        Map<String, Object> version = artifactForOwner(ownerAccountId, artifactVersionId);
        String caseId = String.valueOf(version.get("case_id"));
        cases.lockOwned(ownerAccountId, caseId);
        UUID reviewId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.review_records(review_id, artifact_version_id, case_id, status, actor_id, comment)
                VALUES (?, ?, ?::uuid, 'pending', ?, ?)
                """, reviewId, artifactVersionId, caseId, ownerAccountId, comment);
        return reviewView(reviewId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> listReviews(UUID ownerAccountId, UUID artifactVersionId) {
        artifactForOwner(ownerAccountId, artifactVersionId);
        List<Map<String, Object>> items = jdbc.query("""
                SELECT review_id, artifact_version_id, case_id, status, decision, actor_id,
                       comment, created_at, decided_at
                FROM app.review_records WHERE artifact_version_id = ?
                ORDER BY created_at DESC
                """, this::mapReview, artifactVersionId);
        return Map.of("items", items);
    }

    private Map<String, Object> artifactForOwner(UUID ownerAccountId, UUID artifactVersionId) {
        requireOwner(ownerAccountId);
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT s.case_id, s.kind, v.artifact_stream_id
                FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                JOIN app.cases c ON c.id = s.case_id
                WHERE v.artifact_version_id = ? AND c.owner_account_id = ?
                """, artifactVersionId, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "ARTIFACT_NOT_FOUND", "工件版本不存在或不可访问");
        }
        return rows.get(0);
    }

    private Map<String, Object> reviewView(UUID reviewId) {
        return jdbc.queryForObject("""
                SELECT review_id, artifact_version_id, case_id, status, decision, actor_id,
                       comment, created_at, decided_at
                FROM app.review_records WHERE review_id = ?
                """, this::mapReview, reviewId);
    }

    private Map<String, Object> mapReview(ResultSet rs, int ignored) throws SQLException {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("reviewId", rs.getObject("review_id", UUID.class));
        view.put("artifactVersionId", rs.getObject("artifact_version_id", UUID.class));
        view.put("caseId", rs.getString("case_id"));
        view.put("status", rs.getString("status"));
        view.put("decision", rs.getString("decision"));
        view.put("actorId", rs.getObject("actor_id", UUID.class));
        view.put("comment", rs.getString("comment"));
        view.put("createdAt", rs.getObject("created_at", OffsetDateTime.class));
        view.put("decidedAt", rs.getObject("decided_at", OffsetDateTime.class));
        return view;
    }

    // ---------- drafts ----------

    @Transactional(readOnly = true)
    public Map<String, Object> draftHead(UUID ownerAccountId, String draftId) {
        String resolved = ids.draftId(draftId);
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT h.draft_id, h.case_id, h.artifact_stream_id, h.approved_version_id,
                       h.stale, h.stale_reason, h.updated_at, s.latest_version_id
                FROM app.draft_head h
                JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                JOIN app.cases c ON c.id = h.case_id
                WHERE h.draft_id = ?::uuid AND c.owner_account_id = ?
                """, resolved, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DRAFT_NOT_FOUND", "文书不存在或不可访问");
        }
        Map<String, Object> r = rows.get(0);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("draftId", r.get("draft_id"));
        view.put("caseId", r.get("case_id"));
        view.put("streamId", r.get("artifact_stream_id"));
        view.put("latestVersionId", r.get("latest_version_id"));
        view.put("approvedVersionId", r.get("approved_version_id"));
        view.put("effectivelyApproved",
                r.get("approved_version_id") != null && !Boolean.TRUE.equals(r.get("stale")));
        view.put("stale", r.get("stale"));
        view.put("staleReason", r.get("stale_reason"));
        view.put("updatedAt", r.get("updated_at"));
        return view;
    }

    // ---------- archives ----------

    @Transactional
    public Map<String, Object> createArchive(UUID ownerAccountId, String caseId, String profile) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return archives.create(caseId,
                profile == null || profile.isBlank() ? CaseArchiveService.PROFILE_CASE_FULL : profile.trim(),
                ownerAccountId);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> archive(UUID ownerAccountId, String caseId, UUID archiveId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT archive_id, archive_version, archive_profile, facts_version_id,
                       manifest_hash, created_at
                FROM app.case_archive WHERE archive_id = ? AND case_id = ?::uuid
                """, archiveId, caseId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "ARCHIVE_NOT_FOUND", "归档不存在或不可访问");
        }
        Map<String, Object> r = rows.get(0);
        List<Map<String, Object>> items = jdbc.query("""
                SELECT artifact_version_id, role FROM app.case_archive_item WHERE archive_id = ?
                """, (rs, ignored) -> Map.of(
                "artifactVersionId", rs.getString(1), "role", rs.getString(2)), archiveId);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("archiveId", r.get("archive_id"));
        view.put("caseId", caseId);
        view.put("archiveVersion", r.get("archive_version"));
        view.put("archiveProfile", r.get("archive_profile"));
        view.put("factsVersionId", r.get("facts_version_id"));
        view.put("manifestHash", r.get("manifest_hash"));
        view.put("createdAt", r.get("created_at"));
        view.put("items", items);
        return view;
    }

    private Object parseJson(Object raw) {
        if (raw == null) {
            return null;
        }
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().readValue(String.valueOf(raw), Object.class);
        } catch (Exception ex) {
            throw new IllegalStateException("invalid jsonb payload", ex);
        }
    }

    private static void requireOwner(UUID ownerAccountId) {
        if (ownerAccountId == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "session required");
        }
    }
}
