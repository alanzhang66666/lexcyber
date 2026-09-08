package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FactService {
    public static final String SCHEMA_VERSION = "case.facts.v1";
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final CaseService cases;

    public FactService(JdbcTemplate jdbc, ObjectMapper objectMapper, CaseService cases) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.cases = cases;
    }

    @Transactional(readOnly = true)
    public FactView get(UUID ownerAccountId, String caseId) {
        cases.requireOwned(ownerAccountId, caseId);
        List<FactView> rows = jdbc.query(selectSql() + " WHERE case_id = ?", this::map, caseId);
        if (rows.isEmpty()) {
            return new FactView(caseId, SCHEMA_VERSION, "draft", List.of(), OffsetDateTime.now(), null);
        }
        return rows.get(0);
    }

    @Transactional
    public FactView replace(UUID ownerAccountId, String caseId, FactUpdate update) {
        cases.requireOwned(ownerAccountId, caseId);
        FactView current = lockedOrEmpty(caseId);
        if ("confirmed".equals(current.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_CONFIRMED", "已确认的事实不能再修改");
        }
        List<FactItem> items = normalize(update == null ? null : update.items());
        upsert(caseId, "draft", items, null);
        return requireRow(caseId);
    }

    @Transactional
    public FactView confirm(UUID ownerAccountId, String caseId) {
        cases.requireOwned(ownerAccountId, caseId);
        FactView current = lockedOrEmpty(caseId);
        if ("confirmed".equals(current.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_CONFIRMED", "事实已确认");
        }
        upsert(caseId, "confirmed", current.items(), OffsetDateTime.now());
        return requireRow(caseId);
    }

    private FactView lockedOrEmpty(String caseId) {
        List<FactView> rows = jdbc.query(selectSql() + " WHERE case_id = ? FOR UPDATE", this::map, caseId);
        if (rows.isEmpty()) {
            return new FactView(caseId, SCHEMA_VERSION, "draft", List.of(), OffsetDateTime.now(), null);
        }
        return rows.get(0);
    }

    private void upsert(String caseId, String status, List<FactItem> items, OffsetDateTime confirmedAt) {
        jdbc.update("""
                INSERT INTO app.case_facts(case_id, schema_version, status, items_json, updated_at, confirmed_at)
                VALUES (?, ?, ?, ?::jsonb, now(), ?)
                ON CONFLICT (case_id) DO UPDATE
                SET schema_version = EXCLUDED.schema_version,
                    status = EXCLUDED.status,
                    items_json = EXCLUDED.items_json,
                    updated_at = now(),
                    confirmed_at = EXCLUDED.confirmed_at
                """,
                caseId, SCHEMA_VERSION, status, writeJson(items), confirmedAt);
    }

    private FactView requireRow(String caseId) {
        return jdbc.query(selectSql() + " WHERE case_id = ?", this::map, caseId).stream()
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("facts row missing after write"));
    }

    private List<FactItem> normalize(List<FactItem> items) {
        if (items == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "items is required");
        }
        List<FactItem> normalized = new ArrayList<>();
        for (FactItem item : items) {
            if (item == null || item.key() == null || item.key().isBlank() || item.value() == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "each fact item needs key and value");
            }
            String id = item.id() == null || item.id().isBlank() ? UUID.randomUUID().toString() : item.id().trim();
            normalized.add(new FactItem(id, item.key().trim(), item.value(), item.locator(), item.sourceDocumentId()));
        }
        return List.copyOf(normalized);
    }

    private String selectSql() {
        return "SELECT case_id, schema_version, status, items_json, updated_at, confirmed_at FROM app.case_facts";
    }

    private FactView map(ResultSet rs, int ignored) throws SQLException {
        return new FactView(
                rs.getString("case_id"),
                rs.getString("schema_version"),
                rs.getString("status"),
                readItems(rs.getString("items_json")),
                rs.getObject("updated_at", OffsetDateTime.class),
                rs.getObject("confirmed_at", OffsetDateTime.class));
    }

    private List<FactItem> readItems(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            List<Map<String, Object>> raw = objectMapper.readValue(json, new TypeReference<>() {});
            List<FactItem> items = new ArrayList<>();
            for (Map<String, Object> row : raw) {
                items.add(new FactItem(
                        stringValue(row.get("id")),
                        stringValue(row.get("key")),
                        stringValue(row.get("value")),
                        stringValue(row.get("locator")),
                        stringValue(row.get("sourceDocumentId"))));
            }
            return List.copyOf(items);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("invalid facts json", ex);
        }
    }

    private String writeJson(List<FactItem> items) {
        try {
            return objectMapper.writeValueAsString(items == null ? List.of() : items);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("unable to serialize facts", ex);
        }
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }
}
