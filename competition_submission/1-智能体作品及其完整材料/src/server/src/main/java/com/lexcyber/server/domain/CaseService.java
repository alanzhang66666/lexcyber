package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.ArrayList;
import java.util.LinkedHashMap;
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
    private final ObjectMapper canonicalObjectMapper;

    public CaseService(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.canonicalObjectMapper = objectMapper.copy()
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    }

    @Transactional
    public CaseView create(UUID ownerAccountId, CaseCreate request) {
        return create(ownerAccountId, request, null);
    }

    @Transactional
    public CaseView create(UUID ownerAccountId, CaseCreate request, String idempotencyKey) {
        String title = request.title().trim();
        Map<String, Object> metadata = request.metadata() == null ? Map.of() : request.metadata();
        String key = normalizeIdempotencyKey(idempotencyKey);
        String requestHash = key == null ? null : caseRequestHash(request, metadata);
        if (key != null) {
            CaseView replay = claimCaseIdempotency(ownerAccountId, key, requestHash);
            if (replay != null) return replay;
        }
        DuplicateKeyException last = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            String id = DocumentPolicies.newCaseId();
            try {
                jdbc.update("""
                        INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?::jsonb)
                        """,
                        id, ownerAccountId, title, request.jurisdiction(), request.asOfDate(), writeJson(metadata));
                if (key != null) {
                    jdbc.update("""
                            UPDATE app.case_create_idempotency SET case_id = ?
                            WHERE account_id = ? AND idempotency_key = ? AND request_hash = ?
                            """, id, ownerAccountId, key, requestHash);
                }
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

    @Transactional
    public CaseView bindEventDocument(UUID ownerAccountId, String caseId, String eventId,
                                      CaseEventDocumentUpdate request) {
        CaseView current = lockOwned(ownerAccountId, caseId);
        if (eventId == null || eventId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "eventId is required");
        }
        String documentId = request.documentId() == null ? "" : request.documentId().trim();
        if (documentId.isEmpty() || (request.locator() != null && request.locator().isBlank())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "documentId and locator must be nonblank");
        }
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM app.documents WHERE id = ? AND case_id = ?",
                Long.class, documentId, caseId);
        if (count == null || count == 0L) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DOCUMENT_NOT_FOUND", "材料不存在或不属于该案件");
        }

        Map<String, Object> metadata = new LinkedHashMap<>(current.metadata());
        Object relationsValue = metadata.get("relations");
        if (!(relationsValue instanceof Map<?, ?> relationsRaw)) {
            throw new ApiException(HttpStatus.NOT_FOUND, "EVENT_NOT_FOUND", "关系事件不存在");
        }
        Map<String, Object> relations = new LinkedHashMap<>();
        relationsRaw.forEach((key, value) -> relations.put(String.valueOf(key), value));
        Object eventsValue = relations.get("events");
        if (!(eventsValue instanceof List<?> eventsRaw)) {
            throw new ApiException(HttpStatus.NOT_FOUND, "EVENT_NOT_FOUND", "关系事件不存在");
        }
        List<Object> events = new ArrayList<>(eventsRaw);
        int matches = 0;
        for (int i = 0; i < events.size(); i++) {
            if (!(events.get(i) instanceof Map<?, ?> eventRaw)
                    || !eventId.equals(eventRaw.get("eventId"))) continue;
            matches++;
            Map<String, Object> event = new LinkedHashMap<>();
            eventRaw.forEach((key, value) -> event.put(String.valueOf(key), value));
            event.put("documentId", documentId);
            if (request.locator() != null) event.put("locator", request.locator().trim());
            events.set(i, event);
        }
        if (matches == 0) {
            throw new ApiException(HttpStatus.NOT_FOUND, "EVENT_NOT_FOUND", "关系事件不存在");
        }
        if (matches > 1) {
            throw new ApiException(HttpStatus.CONFLICT, "DUPLICATE_EVENT_ID", "关系事件 ID 不唯一");
        }
        relations.put("events", events);
        metadata.put("relations", relations);
        jdbc.update("UPDATE app.cases SET metadata_json = ?::jsonb, updated_at = now() WHERE id = ? AND owner_account_id = ?",
                writeJson(metadata), caseId, ownerAccountId);
        return requireOwned(ownerAccountId, caseId);
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

    private CaseView claimCaseIdempotency(UUID ownerAccountId, String key, String requestHash) {
        jdbc.update("""
                INSERT INTO app.case_create_idempotency(account_id, idempotency_key, request_hash, case_id)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT (account_id, idempotency_key) DO NOTHING
                """, ownerAccountId, key, requestHash);
        Map<String, Object> row = jdbc.queryForMap("""
                SELECT request_hash, case_id
                FROM app.case_create_idempotency
                WHERE account_id = ? AND idempotency_key = ?
                FOR UPDATE
                """, ownerAccountId, key);
        if (!requestHash.equals(String.valueOf(row.get("request_hash")))) {
            throw new ApiException(HttpStatus.CONFLICT, "IDEMPOTENCY_CONFLICT",
                    "相同幂等键已用于不同案件内容");
        }
        Object caseId = row.get("case_id");
        return caseId == null ? null : requireOwned(ownerAccountId, String.valueOf(caseId));
    }

    private String caseRequestHash(CaseCreate request, Map<String, Object> metadata) {
        Map<String, Object> canonical = new LinkedHashMap<>();
        canonical.put("title", request.title().trim());
        canonical.put("jurisdiction", request.jurisdiction());
        canonical.put("asOfDate", request.asOfDate());
        canonical.put("metadata", metadata);
        try {
            String json = canonicalObjectMapper.writeValueAsString(canonical);
            return DocumentPolicies.sha256Hex(json.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("unable to hash case request", ex);
        }
    }

    private static String normalizeIdempotencyKey(String value) {
        if (value == null || value.isBlank()) return null;
        String key = value.trim();
        if (key.length() > 128) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "Idempotency-Key is too long");
        }
        return key;
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
