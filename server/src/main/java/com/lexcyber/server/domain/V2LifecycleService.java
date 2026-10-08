package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.EngineCapabilitiesClient;
import com.lexcyber.server.engine.EngineRegistryClient;
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
    private final EngineRegistryClient registry;

    public V2LifecycleService(JdbcTemplate jdbc, CaseService cases, FactsBaselineService baseline,
                              ModuleConfirmationService moduleConfirmation,
                              DraftApprovalService draftApproval, CaseArchiveService archives,
                              EngineCapabilitiesClient capabilities, TaskService tasks) {
        this(jdbc, cases, baseline, moduleConfirmation, draftApproval, archives, capabilities, tasks,
                new EngineRegistryClient());
    }

    @org.springframework.beans.factory.annotation.Autowired
    public V2LifecycleService(JdbcTemplate jdbc, CaseService cases, FactsBaselineService baseline,
                              ModuleConfirmationService moduleConfirmation,
                              DraftApprovalService draftApproval, CaseArchiveService archives,
                              EngineCapabilitiesClient capabilities, TaskService tasks,
                              EngineRegistryClient registry) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.ids = new IdentityService(jdbc);
        this.baseline = baseline;
        this.moduleConfirmation = moduleConfirmation;
        this.draftApproval = draftApproval;
        this.archives = archives;
        this.capabilities = capabilities;
        this.tasks = tasks;
        this.registry = registry;
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

    @Transactional
    public List<Map<String, Object>> listFactsVersions(UUID ownerAccountId, String caseId) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
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

    private void refreshModuleHead(String caseId, String module, Map<String, Object> row) {
        UUID version = (UUID) row.get("confirmed_version_id");
        if (version == null || Boolean.TRUE.equals(row.get("stale"))) return;
        try {
            registry.requireValid(jdbc, version);
        } catch (ApiException invalid) {
            if (!"DEPENDENCY_STALE".equals(invalid.code())) throw invalid;
            jdbc.update("""
                    UPDATE app.module_head SET stale=true, stale_reason='dependency_changed', updated_at=now()
                    WHERE case_id = ?::uuid AND module = ? AND confirmed_version_id = ? AND NOT stale
                    """, caseId, module, version);
            new StalePropagationService(jdbc).propagateArtifactSuperseded(caseId, version, "dependency_changed");
        }
    }

    // ---------- module head ----------

    @Transactional
    public Map<String, Object> moduleHead(UUID ownerAccountId, String caseId, String module) {
        registry.lockBarrier(jdbc);
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
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
        refreshModuleHead(caseId, resolved, r);
        rows = jdbc.queryForList("""
                SELECT h.artifact_stream_id, h.confirmed_version_id, h.stale, h.stale_reason, h.updated_at,
                       s.latest_version_id
                FROM app.module_head h JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                WHERE h.case_id = ?::uuid AND h.module = ?
                """, caseId, resolved);
        r = rows.get(0);
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
        return dispatchModuleExecution(ownerAccountId, caseId, module, null);
    }

    @Transactional
    public Map<String, Object> dispatchModuleExecution(UUID ownerAccountId, String caseId, String module,
                                                      Map<String, Object> body) {
        registry.lockBarrier(jdbc);
        CaseView caseView = cases.lockOwned(ownerAccountId, caseId);
        caseId = caseView.id();
        if (caseView.asOfDate() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "AS_OF_DATE_REQUIRED", "案件必须先设置基准日期");
        }
        String taskType = switch (module) {
            case "compliance" -> TaskPolicies.COMPLIANCE_ANALYZE;
            case "conviction" -> TaskPolicies.CONVICTION_ANALYZE;
            case "sentencing" -> TaskPolicies.SENTENCING_CALCULATE;
            default -> throw new ApiException(HttpStatus.NOT_FOUND, "MODULE_NOT_FOUND", "未知模块");
        };
        List<Map<String, Object>> requestedCharges = RequestedCharges.freeze(module, body);
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
        metadata.put("asOfDate", caseView.asOfDate().toString());
        if (ModulePolicies.CONVICTION.equals(module)) {
            metadata.put("requestedCharges", requestedCharges);
        }
        if (ModulePolicies.SENTENCING.equals(module)) {
            UUID convictionVersionId = moduleConfirmation.requireEffectiveConviction(caseId);
            metadata.put("artifactVersions", Map.of("conviction", convictionVersionId.toString()));
        }
        TaskView task = tasks.createModuleTask(
                new TaskCreate("module:" + module, caseId, null, metadata));
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("taskId", task.id());
        view.put("executionId", task.executionId());
        view.put("status", task.status());
        view.put("module", module);
        view.put("state", "queued");
        view.put("caseId", caseId);
        view.put("createdAt", task.createdAt());
        return view;
    }

    /**
     * 文书渲染派发：doc_type 必须有 approved 模板（能力门闩），confirmed facts
     * + 上游模块最新已发布 payload 一并嵌入 metadata（INV-DATA-OWN-002）。
     */
    @Transactional
    public Map<String, Object> dispatchDraftRender(UUID ownerAccountId, String caseId, String docType) {
        registry.lockBarrier(jdbc);
        CaseView caseView = cases.lockOwned(ownerAccountId, caseId);
        caseId = caseView.id();
        if (caseView.asOfDate() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "AS_OF_DATE_REQUIRED", "案件必须先设置基准日期");
        }
        if (docType == null || docType.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "DOC_TYPE_MISSING", "需要 docType");
        }
        if (!capabilities.templateAvailable(docType)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "DRAFT_RENDER_UNAVAILABLE",
                    "文书渲染能力未启用：doc_type " + docType + " 无已会签模板");
        }
        UUID factsVersionId = baseline.requireConfirmedVersionId(caseId);
        Object factsPayload = baseline.versionDetail(caseId, factsVersionId).get("payload");
        UUID draftId = ensureRenderedDraft(ownerAccountId, caseId, docType);
        ModuleInputs inputs = confirmedModuleInputs(caseId);
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("taskType", TaskPolicies.DRAFT_RENDER);
        metadata.put("docType", docType);
        metadata.put("draftId", draftId.toString());
        metadata.put("factsVersionId", factsVersionId.toString());
        metadata.put("factsSnapshot", factsPayload);
        metadata.put("asOfDate", caseView.asOfDate().toString());
        metadata.put("artifacts", inputs.payloads());
        metadata.put("artifactVersions", inputs.versionIds());
        TaskView task = tasks.createModuleTask(
                new TaskCreate("draft:" + docType, caseId, null, metadata));
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("taskId", task.id());
        view.put("executionId", task.executionId());
        view.put("status", task.status());
        view.put("docType", docType);
        view.put("draftId", draftId);
        return view;
    }

    private UUID ensureRenderedDraft(UUID ownerAccountId, String caseId, String docType) {
        UUID draftId = jdbc.queryForObject("""
                INSERT INTO app.case_drafts(id, case_id, draft_type, render_doc_type, updated_by)
                VALUES (?, ?::uuid, ?, ?, ?)
                ON CONFLICT (case_id, render_doc_type) WHERE render_doc_type IS NOT NULL
                DO UPDATE SET render_doc_type = EXCLUDED.render_doc_type
                RETURNING id
                """, UUID.class, UUID.randomUUID(), caseId, docType, docType, ownerAccountId);
        UUID streamId = new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc))
                .ensureStreamLocked(caseId, "draft", "draft:" + draftId);
        jdbc.update("""
                INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id)
                VALUES (?, ?::uuid, ?) ON CONFLICT (draft_id) DO NOTHING
                """, draftId, caseId, streamId);
        return draftId;
    }

    /** Freeze payloads and their exact IDs together; pending/stale results are not draft inputs. */
    private ModuleInputs confirmedModuleInputs(String caseId) {
        // Never hide a withdrawn registry dependency by silently omitting its
        // stale head. Ordinary facts/publishing staleness, however, must still
        // permit a facts-only template or a blocked diagnostic without using
        // that old module payload.
        for (UUID confirmed : jdbc.query("""
                SELECT confirmed_version_id FROM app.module_head
                WHERE case_id = ?::uuid AND confirmed_version_id IS NOT NULL
                ORDER BY module
                """, (rs, ignored) -> rs.getObject(1, UUID.class), caseId)) {
            registry.requireValid(jdbc, confirmed);
        }
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT s.kind, v.artifact_version_id, v.payload::text AS payload
                FROM app.module_head h
                JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                JOIN app.artifact_version v ON v.artifact_version_id = h.confirmed_version_id
                WHERE h.case_id = ?::uuid AND NOT h.stale
                  AND s.latest_version_id = h.confirmed_version_id
                  AND v.outcome_status <> 'blocked'
                ORDER BY s.kind
                """, caseId);
        Map<String, Object> out = new LinkedHashMap<>();
        Map<String, String> versions = new LinkedHashMap<>();
        for (Map<String, Object> r : rows) {
            UUID versionId = (UUID) r.get("artifact_version_id");
            UUID effective = moduleConfirmation.requireEffectiveArtifactVersion(
                    caseId, String.valueOf(r.get("kind")));
            if (!versionId.equals(effective)) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                        "上游模块在渲染前已变更，必须重新派发");
            }
            out.put(String.valueOf(r.get("kind")), parseJson(r.get("payload")));
            versions.put(String.valueOf(r.get("kind")), versionId.toString());
        }
        return new ModuleInputs(out, versions);
    }

    private record ModuleInputs(Map<String, Object> payloads, Map<String, String> versionIds) {}

    /** UUID draft streams expose the descriptor's docType, independently of scope syntax. */
    @Transactional(readOnly = true)
    public Map<String, Object> listDraftStreams(UUID ownerAccountId, String caseId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT s.artifact_stream_id, d.id AS draft_id, d.draft_type,
                       s.latest_version_id, s.updated_at
                FROM app.artifact_stream s
                JOIN app.draft_head h ON h.artifact_stream_id = s.artifact_stream_id
                JOIN app.case_drafts d ON d.id = h.draft_id
                WHERE s.case_id = ?::uuid AND s.kind = 'draft'
                ORDER BY s.scope_key
                """, caseId);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map<String, Object> r : rows) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("streamId", r.get("artifact_stream_id"));
            item.put("draftId", r.get("draft_id"));
            item.put("docType", r.get("draft_type"));
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
        registry.lockBarrier(jdbc);
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

    @Transactional
    public Map<String, Object> draftHead(UUID ownerAccountId, String draftId) {
        registry.lockBarrier(jdbc);
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
        LegalAnalysisContext.lockCase(jdbc, String.valueOf(r.get("case_id")));
        r = jdbc.queryForMap("""
                SELECT h.draft_id, h.case_id, h.artifact_stream_id, h.approved_version_id,
                       h.stale, h.stale_reason, h.updated_at, s.latest_version_id
                FROM app.draft_head h JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                WHERE h.draft_id = ?::uuid
                """, resolved);
        UUID approved = (UUID) r.get("approved_version_id");
        if (approved != null && !Boolean.TRUE.equals(r.get("stale"))) {
            try {
                registry.requireValid(jdbc, approved);
            } catch (ApiException invalid) {
                if (!"DEPENDENCY_STALE".equals(invalid.code())) throw invalid;
                jdbc.update("""
                        UPDATE app.draft_head SET stale=true, stale_reason='dependency_changed', updated_at=now()
                        WHERE draft_id = ?::uuid AND approved_version_id = ? AND NOT stale
                        """, resolved, approved);
                new StalePropagationService(jdbc).propagateArtifactSuperseded(
                        String.valueOf(r.get("case_id")), approved, "dependency_changed");
                r = jdbc.queryForMap("""
                        SELECT h.draft_id, h.case_id, h.artifact_stream_id, h.approved_version_id,
                               h.stale, h.stale_reason, h.updated_at, s.latest_version_id
                        FROM app.draft_head h JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                        WHERE h.draft_id = ?::uuid
                        """, resolved);
            }
        }
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
