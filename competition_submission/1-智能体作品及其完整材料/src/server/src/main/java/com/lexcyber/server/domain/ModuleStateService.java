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
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ModuleStateService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final CaseService cases;

    public ModuleStateService(JdbcTemplate jdbc, ObjectMapper objectMapper, CaseService cases) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.cases = cases;
    }

    @Transactional(readOnly = true)
    public ModuleStateView get(UUID ownerAccountId, String caseId, String module) {
        cases.requireOwned(ownerAccountId, caseId);
        String resolved = ModulePolicies.requireModule(module);
        List<ModuleStateView> rows = jdbc.query(selectSql() + " WHERE case_id = ? AND module = ?", this::map, caseId, resolved);
        FactsClock facts = factsClock(caseId);
        if (rows.isEmpty()) {
            return empty(caseId, resolved, facts);
        }
        return withStale(rows.get(0), facts);
    }

    @Transactional
    public ModuleStateView replace(UUID ownerAccountId, String caseId, String module, ModuleStateUpdate update) {
        cases.lockOwned(ownerAccountId, caseId);
        String resolved = ModulePolicies.requireModule(module);
        if (update == null || update.version() == null || update.content() == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "content and version are required");
        }
        ModuleStateView current = lockedOrEmpty(caseId, resolved);
        if ("confirmed".equals(current.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_CONFIRMED", "已确认的模块不能再修改");
        }
        if (update.version() != current.version()) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_VERSION_CONFLICT", "模块版本已变更");
        }
        String applicability = update.applicability() == null
                ? current.applicability()
                : ModulePolicies.requireApplicability(update.applicability());
        FactsClock facts = factsClock(caseId);
        int nextVersion = current.version() + 1;
        int changed = jdbc.update("""
                INSERT INTO app.case_module_states(
                    case_id, module, schema_version, applicability, status, version, content_json,
                    facts_updated_at, source_version, updated_by, updated_at, confirmed_at)
                VALUES (?, ?, ?, ?, 'draft', ?, ?::jsonb, ?, ?, ?, now(), NULL)
                ON CONFLICT (case_id, module) DO UPDATE
                SET schema_version = EXCLUDED.schema_version,
                    applicability = EXCLUDED.applicability,
                    status = 'draft',
                    version = EXCLUDED.version,
                    content_json = EXCLUDED.content_json,
                    facts_updated_at = EXCLUDED.facts_updated_at,
                    source_version = EXCLUDED.source_version,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now(),
                    confirmed_at = NULL
                WHERE app.case_module_states.status <> 'confirmed'
                  AND app.case_module_states.version = ?
                """,
                caseId, resolved, ModulePolicies.SCHEMA_VERSION, applicability, nextVersion,
                writeJson(update.content()), facts.updatedAt(),
                blankToNull(update.sourceVersion()), ownerAccountId, current.version());
        if (changed == 0) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_VERSION_CONFLICT", "模块版本已变更");
        }
        return requireRow(caseId, resolved);
    }

    @Transactional
    public ModuleStateView confirm(UUID ownerAccountId, String caseId, String module) {
        cases.lockOwned(ownerAccountId, caseId);
        String resolved = ModulePolicies.requireModule(module);
        ModuleStateView current = lockedOrEmpty(caseId, resolved);
        if ("confirmed".equals(current.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "MODULE_CONFIRMED", "模块已确认");
        }
        jdbc.update("""
                INSERT INTO app.case_module_states(
                    case_id, module, schema_version, applicability, status, version, content_json,
                    facts_updated_at, source_version, updated_by, updated_at, confirmed_at)
                VALUES (?, ?, ?, ?, 'confirmed', ?, ?::jsonb, ?, ?, ?, now(), now())
                ON CONFLICT (case_id, module) DO UPDATE
                SET status = 'confirmed',
                    confirmed_at = now(),
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                WHERE app.case_module_states.status <> 'confirmed'
                """,
                caseId, resolved, ModulePolicies.SCHEMA_VERSION, current.applicability(), current.version(),
                writeJson(current.content()), current.factsUpdatedAt(), current.sourceVersion(), ownerAccountId);
        return requireRow(caseId, resolved);
    }

    private ModuleStateView lockedOrEmpty(String caseId, String module) {
        List<ModuleStateView> rows = jdbc.query(
                selectSql() + " WHERE case_id = ? AND module = ? FOR UPDATE", this::map, caseId, module);
        FactsClock facts = factsClock(caseId);
        if (rows.isEmpty()) {
            return empty(caseId, module, facts);
        }
        return withStale(rows.get(0), facts);
    }

    private ModuleStateView requireRow(String caseId, String module) {
        FactsClock facts = factsClock(caseId);
        return jdbc.query(selectSql() + " WHERE case_id = ? AND module = ?", this::map, caseId, module).stream()
                .findFirst()
                .map(row -> withStale(row, facts))
                .orElseThrow(() -> new IllegalStateException("module row missing after write"));
    }

    private ModuleStateView empty(String caseId, String module, FactsClock facts) {
        return new ModuleStateView(
                caseId, module, ModulePolicies.SCHEMA_VERSION, "unknown", "draft", 0, Map.of(),
                null, null, factsStale(null, facts),
                null, OffsetDateTime.now(), null);
    }

    private ModuleStateView withStale(ModuleStateView row, FactsClock facts) {
        OffsetDateTime snapshot = facts.exist() ? row.factsUpdatedAt() : null;
        return new ModuleStateView(
                row.caseId(), row.module(), row.schemaVersion(), row.applicability(), row.status(),
                row.version(), row.content(), row.sourceVersion(), snapshot, factsStale(row.factsUpdatedAt(), facts),
                row.updatedBy(), row.updatedAt(), row.confirmedAt());
    }

    private static boolean factsStale(OffsetDateTime snapshot, FactsClock facts) {
        if (!facts.exist()) {
            return false;
        }
        return snapshot == null || facts.updatedAt() == null || !snapshot.isEqual(facts.updatedAt());
    }

    private FactsClock factsClock(String caseId) {
        List<OffsetDateTime> rows = jdbc.query(
                "SELECT updated_at FROM app.case_facts WHERE case_id = ?",
                (rs, ignored) -> rs.getObject("updated_at", OffsetDateTime.class),
                caseId);
        if (rows.isEmpty()) {
            return new FactsClock(false, null);
        }
        return new FactsClock(true, rows.get(0));
    }

    private String selectSql() {
        return """
                SELECT case_id, module, schema_version, applicability, status, version, content_json,
                       facts_updated_at, source_version, updated_by, updated_at, confirmed_at
                FROM app.case_module_states
                """;
    }

    private ModuleStateView map(ResultSet rs, int ignored) throws SQLException {
        return new ModuleStateView(
                rs.getString("case_id"),
                rs.getString("module"),
                rs.getString("schema_version"),
                rs.getString("applicability"),
                rs.getString("status"),
                rs.getInt("version"),
                readContent(rs.getString("content_json")),
                rs.getString("source_version"),
                rs.getObject("facts_updated_at", OffsetDateTime.class),
                false,
                rs.getObject("updated_by", UUID.class),
                rs.getObject("updated_at", OffsetDateTime.class),
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

    private record FactsClock(boolean exist, OffsetDateTime updatedAt) {
    }
}
