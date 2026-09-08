package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CaseService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public CaseService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public CaseView create(UUID ownerAccountId, CaseCreate request) {
        String title = request.title().trim();
        Map<String, Object> metadata = request.metadata() == null ? Map.of() : request.metadata();
        DuplicateKeyException last = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            String id = DocumentPolicies.newCaseId();
            try {
                jdbc.update("""
                        INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?::jsonb)
                        """,
                        id, ownerAccountId, title, request.jurisdiction(), request.asOfDate(), writeJson(metadata));
                return requireOwned(ownerAccountId, id);
            } catch (DuplicateKeyException duplicate) {
                last = duplicate;
            }
        }
        throw new IllegalStateException("unable to allocate a case id", last);
    }

    @Transactional(readOnly = true)
    public PageResponse<CaseView> list(UUID ownerAccountId, int page, int size) {
        requirePage(page, size);
        List<CaseView> items = jdbc.query("""
                SELECT id, title, jurisdiction, as_of_date, metadata_json, created_at, updated_at
                FROM app.cases
                WHERE owner_account_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """, this::map, ownerAccountId, size, page * size);
        Long total = jdbc.queryForObject("SELECT COUNT(*) FROM app.cases WHERE owner_account_id = ?", Long.class, ownerAccountId);
        return new PageResponse<>(items, page, size, total == null ? 0L : total);
    }

    @Transactional(readOnly = true)
    public CaseView requireOwned(UUID ownerAccountId, String caseId) {
        return findOwned(ownerAccountId, caseId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "CASE_NOT_FOUND", "案件不存在或不可访问"));
    }

    @Transactional
    public CaseView lockOwned(UUID ownerAccountId, String caseId) {
        List<CaseView> rows = jdbc.query("""
                SELECT id, title, jurisdiction, as_of_date, metadata_json, created_at, updated_at
                FROM app.cases
                WHERE id = ? AND owner_account_id = ?
                FOR UPDATE
                """, this::map, caseId, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "CASE_NOT_FOUND", "案件不存在或不可访问");
        }
        return rows.get(0);
    }

    @Transactional(readOnly = true)
    public Optional<CaseView> findOwned(UUID ownerAccountId, String caseId) {
        return jdbc.query("""
                SELECT id, title, jurisdiction, as_of_date, metadata_json, created_at, updated_at
                FROM app.cases
                WHERE id = ? AND owner_account_id = ?
                """, this::map, caseId, ownerAccountId).stream().findFirst();
    }

    private CaseView map(ResultSet rs, int ignored) throws SQLException {
        return new CaseView(
                rs.getString("id"),
                rs.getString("title"),
                rs.getString("jurisdiction"),
                rs.getObject("as_of_date", LocalDate.class),
                parseMap(rs.getString("metadata_json")),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("updated_at", OffsetDateTime.class));
    }

    private Map<String, Object> parseMap(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("invalid case metadata", ex);
        }
    }

    private String writeJson(Map<String, Object> metadata) {
        try {
            return objectMapper.writeValueAsString(metadata == null ? Map.of() : metadata);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("unable to serialize case metadata", ex);
        }
    }

    static void requirePage(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "invalid page");
        }
    }
}
