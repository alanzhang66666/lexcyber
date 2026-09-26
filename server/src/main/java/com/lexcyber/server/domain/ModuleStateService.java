package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * /v1 模块端点适配层（契约冻结）：
 * - 正文/版本 → artifact_version / artifact_stream（唯一事实源）；
 * - 确认状态 → module_head（confirmed_version_id + stale，ADR-0004/0005）；
 * - PUT 走手工发布（execution_id = NULL），confirm 走 ModuleConfirmationService。
 */
@Service
public class ModuleStateService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final CaseService cases;
    private final ArtifactPublicationService artifacts;
    private final ModuleConfirmationService confirmation;
    private final boolean demoImportEnabled;

    public ModuleStateService(JdbcTemplate jdbc, ObjectMapper objectMapper, CaseService cases,
                              ArtifactPublicationService artifacts,
                              ModuleConfirmationService confirmation,
                              @Value("${demo.import.enabled:false}") boolean demoImportEnabled) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.cases = cases;
        this.artifacts = artifacts;
        this.confirmation = confirmation;
        this.demoImportEnabled = demoImportEnabled;
    }

    @Transactional(readOnly = true)
    public ModuleStateView get(UUID ownerAccountId, String caseId, String module) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return view(caseId, ModulePolicies.requireModule(module));
    }

    @Transactional
    public ModuleStateView replace(UUID ownerAccountId, String caseId, String module,
                                   ModuleStateUpdate update) {
        requireWriteEnabled();
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        String resolved = ModulePolicies.requireModule(module);
        if (update == null || update.version() == null || update.content() == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "content and version are required");
        }
        ModuleStateView current = view(caseId, resolved);
        if ("confirmed".equals(current.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_CONFIRMED", "已确认的模块不能再修改");
        }
        if (update.version() != current.version()) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_VERSION_CONFLICT", "模块版本已变更");
        }
        String applicability = update.applicability() == null
                ? current.applicability()
                : ModulePolicies.requireApplicability(update.applicability());
        String payload = writeJson(update.content());
        artifacts.publish(new ArtifactPublicationService.PublishRequest(
                caseId, resolved, "module:" + resolved, ModulePolicies.SCHEMA_VERSION,
                "calculated", payload, null, "{}",
                baselineConfirmed(caseId), List.of(), List.of(),
                null, null, null));
        // 展示元数据留在 slim 行上
        jdbc.update("""
                INSERT INTO app.case_module_states(case_id, module, applicability, source_version,
                                                   updated_by, updated_at)
                VALUES (?::uuid, ?, ?, ?, ?, now())
                ON CONFLICT (case_id, module) DO UPDATE
                SET applicability = EXCLUDED.applicability,
                    source_version = EXCLUDED.source_version,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                """, caseId, resolved, applicability, blankToNull(update.sourceVersion()), ownerAccountId);
        return view(caseId, resolved);
    }

    @Transactional
    public ModuleStateView confirm(UUID ownerAccountId, String caseId, String module) {
        requireWriteEnabled();
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        String resolved = ModulePolicies.requireModule(module);
        ensureHead(caseId, resolved);
        confirmation.confirm(caseId, resolved, ownerAccountId);
        return view(caseId, resolved);
    }

    private void requireWriteEnabled() {
        if (!demoImportEnabled) {
            throw new ApiException(HttpStatus.GONE, "MODULE_WRITE_RETIRED",
                    "模块写层已退役：结果仅由执行发布产生；演示导入需显式开启 DEMO_IMPORT_ENABLED");
        }
    }

    private void ensureHead(String caseId, String module) {
        UUID streamId = artifacts.ensureStreamLocked(caseId, module, "module:" + module);
        jdbc.update("""
                INSERT INTO app.module_head(case_id, module, artifact_stream_id)
                VALUES (?::uuid, ?, ?)
                ON CONFLICT (case_id, module) DO NOTHING
                """, caseId, module, streamId);
    }

    private UUID baselineConfirmed(String caseId) {
        return jdbc.query(
                "SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?::uuid",
                (rs, ignored) -> rs.getObject(1, UUID.class), caseId)
                .stream().filter(java.util.Objects::nonNull).findFirst().orElse(null);
    }

    private ModuleStateView view(String caseId, String module) {
        List<ModuleStateView> rows = jdbc.query("""
                SELECT h.case_id, h.module, h.stale, h.stale_reason, h.confirmed_version_id, h.updated_at AS head_updated,
                       s.latest_version_id, v.version, v.payload::text AS payload,
                       v.schema_version, v.created_at AS version_at,
                       ms.applicability, ms.source_version, ms.updated_by, ms.updated_at AS meta_updated,
                       fh.updated_at AS facts_updated_at, fh.confirmed_facts_version_id,
                       afd.facts_version_id AS dep_facts_version_id,
                       (SELECT MAX(rv.decided_at) FROM app.review_records rv
                        WHERE rv.artifact_version_id = h.confirmed_version_id
                          AND rv.status = 'approved') AS confirmed_at
                FROM app.module_head h
                JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                LEFT JOIN app.artifact_version v ON v.artifact_version_id = s.latest_version_id
                LEFT JOIN app.case_module_states ms ON ms.case_id = h.case_id AND ms.module = h.module
                LEFT JOIN app.facts_head fh ON fh.case_id = h.case_id
                LEFT JOIN app.artifact_facts_dependency afd ON afd.artifact_version_id = s.latest_version_id
                WHERE h.case_id = ?::uuid AND h.module = ?
                """, this::map, caseId, module);
        if (rows.isEmpty()) {
            // 无模块 head：factsStale 仅作展示——事实存在但尚无模块版本承接 → true
            boolean factsExist = jdbc.queryForObject(
                    "SELECT COUNT(*) > 0 FROM app.case_fact WHERE case_id = ?::uuid",
                    Boolean.class, caseId);
            return new ModuleStateView(caseId, module, ModulePolicies.SCHEMA_VERSION, "unknown",
                    "draft", 0, Map.of(), null, null, Boolean.TRUE.equals(factsExist),
                    null, OffsetDateTime.now(), null);
        }
        return rows.get(0);
    }

    private ModuleStateView map(ResultSet rs, int ignored) throws SQLException {
        // head.stale 默认 true 表示"尚无确认基线"（ADR-0004 null 指针语义），
        // 只有 stale_reason 非空才是真实失效事件，才计入展示旗标。
        boolean invalidated = rs.getBoolean("stale") && rs.getString("stale_reason") != null;
        boolean confirmed = rs.getObject("confirmed_version_id") != null && !invalidated;
        OffsetDateTime metaUpdated = rs.getObject("meta_updated", OffsetDateTime.class);
        OffsetDateTime headUpdated = rs.getObject("head_updated", OffsetDateTime.class);
        OffsetDateTime versionAt = rs.getObject("version_at", OffsetDateTime.class);
        OffsetDateTime factsUpdatedAt = rs.getObject("facts_updated_at", OffsetDateTime.class);
        UUID depFv = rs.getObject("dep_facts_version_id", UUID.class);
        UUID confirmedFv = rs.getObject("confirmed_facts_version_id", UUID.class);
        // /v1 展示位（非门闩）：权威失效走 head.stale；此旗标叠加依赖差异与事实时钟
        boolean factsStale = invalidated
                || (depFv != null && !depFv.equals(confirmedFv))
                || (depFv == null && confirmedFv != null)
                || (factsUpdatedAt != null && (versionAt == null || factsUpdatedAt.isAfter(versionAt)));
        return new ModuleStateView(
                rs.getString("case_id"),
                rs.getString("module"),
                rs.getString("schema_version") == null ? ModulePolicies.SCHEMA_VERSION
                        : rs.getString("schema_version"),
                rs.getString("applicability") == null ? "unknown" : rs.getString("applicability"),
                confirmed ? "confirmed" : "draft",
                rs.getInt("version"),
                readContent(rs.getString("payload")),
                rs.getString("source_version"),
                factsUpdatedAt,
                factsStale,
                rs.getObject("updated_by", UUID.class),
                metaUpdated != null ? metaUpdated : (headUpdated != null ? headUpdated : OffsetDateTime.now()),
                rs.getObject("confirmed_at", OffsetDateTime.class));
    }

    private Map<String, Object> readContent(String json) {
        if (json == null || json.isBlank()) {
            return Map.of();
        }
        try {
            Map<String, Object> value = objectMapper.readValue(json, new TypeReference<>() {});
            return value == null ? Map.of() : value;
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("invalid module content json", ex);
        }
    }

    private String writeJson(Map<String, Object> content) {
        try {
            return objectMapper.writeValueAsString(content == null ? Map.of() : content);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("unable to serialize module content", ex);
        }
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }
}
