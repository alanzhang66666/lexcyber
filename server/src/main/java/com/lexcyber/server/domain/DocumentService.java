package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.storage.ObjectStorage;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private static final Logger log = LoggerFactory.getLogger(DocumentService.class);
    private static final String PARSE_QUERY = "解析指定材料，提取正文、段落、表格和原文定位";
    private final JdbcTemplate jdbc;
    private final CaseService cases;
    private final TaskService tasks;
    private final ObjectStorage storage;

    public DocumentService(JdbcTemplate jdbc, CaseService cases, TaskService tasks, ObjectStorage storage) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.tasks = tasks;
        this.storage = storage;
    }

    @Transactional
    public DocumentView upload(UUID ownerAccountId, String caseId, String filename, String contentType, byte[] data,
                               String role, String idempotencyKey) {
        cases.requireOwned(ownerAccountId, caseId);
        if (data == null || data.length == 0) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "file is required");
        }
        String normalizedRole;
        try {
            normalizedRole = DocumentPolicies.requireRole(role);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", ex.getMessage());
        }
        String normalizedName = DocumentPolicies.normalizeFilename(filename);
        if (!DocumentPolicies.isSupported(normalizedName, contentType)) {
            throw new ApiException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_DOCUMENT_TYPE", "仅支持 PDF 或 DOCX 材料");
        }
        String sha256 = DocumentPolicies.sha256Hex(data);
        String requestHash = DocumentPolicies.requestHash(data);
        String resolvedType = contentType == null || contentType.isBlank()
                ? ("pdf".equals(DocumentPolicies.detectFormat(normalizedName, contentType))
                    ? DocumentPolicies.PDF : DocumentPolicies.DOCX)
                : contentType;

        String key = idempotencyKey == null || idempotencyKey.isBlank() ? null : idempotencyKey.trim();
        if (key != null) {
            DocumentView replay = claimIdempotency(ownerAccountId, caseId, key, requestHash);
            if (replay != null) return replay;
        }

        String documentId = allocateDocumentId();
        String storageKey = DocumentPolicies.storageKey(caseId, documentId, sha256);
        storage.put(storageKey, data, resolvedType);
        try {
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("taskType", "document.parse");
            metadata.put("documentId", documentId);
            metadata.put("schemaVersion", "document.parse.v1");
            metadata.put("storageKey", storageKey);
            metadata.put("filename", normalizedName);
            metadata.put("contentType", resolvedType);
            metadata.put("role", normalizedRole);
            metadata.put("format", DocumentPolicies.detectFormat(normalizedName, resolvedType));
            TaskView task = tasks.create(new TaskCreate(PARSE_QUERY, caseId, null, metadata));

            jdbc.update("""
                    INSERT INTO app.documents(id, case_id, filename, content_type, size, role, storage_key, sha256, parse_status, parse_task_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                    """,
                    documentId, caseId, normalizedName, resolvedType, data.length, normalizedRole, storageKey, sha256, task.id());

            if (key != null) {
                jdbc.update("""
                        UPDATE app.upload_idempotency
                        SET document_id = ?
                        WHERE account_id = ? AND case_id = ? AND idempotency_key = ? AND request_hash = ?
                        """,
                        documentId, ownerAccountId, caseId, key, requestHash);
            }
            return requireOwned(ownerAccountId, documentId);
        } catch (RuntimeException ex) {
            try {
                storage.delete(storageKey);
            } catch (RuntimeException deleteError) {
                log.warn("failed to delete object {} after upload rollback", storageKey, deleteError);
            }
            throw ex;
        }
    }

    @Transactional(readOnly = true)
    public PageResponse<DocumentView> list(UUID ownerAccountId, String caseId, String role, int page, int size) {
        cases.requireOwned(ownerAccountId, caseId);
        CaseService.requirePage(page, size);
        if (role != null && !role.isBlank()) {
            try {
                DocumentPolicies.requireRole(role);
            } catch (IllegalArgumentException ex) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", ex.getMessage());
            }
        }
        boolean filterRole = role != null && !role.isBlank();
        String where = filterRole ? " AND d.role = ?" : "";
        Object[] itemsParams = filterRole
                ? new Object[] {caseId, role, size, page * size}
                : new Object[] {caseId, size, page * size};
        List<DocumentView> items = jdbc.query(documentSelect() + " WHERE d.case_id = ?" + where
                + " ORDER BY d.created_at DESC LIMIT ? OFFSET ?", this::map, itemsParams);
        Long total = filterRole
                ? jdbc.queryForObject("SELECT COUNT(*) FROM app.documents d WHERE d.case_id = ? AND d.role = ?", Long.class, caseId, role)
                : jdbc.queryForObject("SELECT COUNT(*) FROM app.documents d WHERE d.case_id = ?", Long.class, caseId);
        return new PageResponse<>(items, page, size, total == null ? 0L : total);
    }

    public record StoredDocument(String id, String caseId, String storageKey, String filename, String contentType) {
    }

    @Transactional(readOnly = true)
    public StoredDocument requireOwnedForParse(UUID ownerAccountId, String documentId) {
        List<StoredDocument> rows = jdbc.query("""
                SELECT d.id, d.case_id, d.storage_key, d.filename, d.content_type
                FROM app.documents d
                JOIN app.cases c ON c.id = d.case_id
                WHERE d.id = ? AND c.owner_account_id = ?
                """,
                (rs, ignored) -> new StoredDocument(
                        rs.getString("id"),
                        rs.getString("case_id"),
                        rs.getString("storage_key"),
                        rs.getString("filename"),
                        rs.getString("content_type")),
                documentId, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DOCUMENT_NOT_FOUND", "材料不存在或不可访问");
        }
        return rows.get(0);
    }

    @Transactional(readOnly = true)
    public DocumentView requireOwned(UUID ownerAccountId, String documentId) {
        List<DocumentView> rows = jdbc.query(documentSelect() + """
                JOIN app.cases c ON c.id = d.case_id
                WHERE d.id = ? AND c.owner_account_id = ?
                """, this::map, documentId, ownerAccountId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DOCUMENT_NOT_FOUND", "材料不存在或不可访问");
        }
        return rows.get(0);
    }

    private DocumentView claimIdempotency(UUID ownerAccountId, String caseId, String key, String requestHash) {
        jdbc.update("""
                INSERT INTO app.upload_idempotency(account_id, case_id, idempotency_key, document_id, request_hash)
                VALUES (?, ?, ?, NULL, ?)
                ON CONFLICT (account_id, case_id, idempotency_key) DO NOTHING
                """, ownerAccountId, caseId, key, requestHash);
        Map<String, Object> row = jdbc.queryForMap("""
                SELECT document_id, request_hash
                FROM app.upload_idempotency
                WHERE account_id = ? AND case_id = ? AND idempotency_key = ?
                FOR UPDATE
                """, ownerAccountId, caseId, key);
        if (!requestHash.equals(String.valueOf(row.get("request_hash")))) {
            throw new ApiException(HttpStatus.CONFLICT, "IDEMPOTENCY_CONFLICT", "相同幂等键已用于不同内容的上传");
        }
        Object documentId = row.get("document_id");
        if (documentId == null) return null;
        return requireOwned(ownerAccountId, String.valueOf(documentId));
    }

    private String allocateDocumentId() {
        for (int attempt = 0; attempt < 3; attempt++) {
            String id = DocumentPolicies.newDocumentId();
            Long count = jdbc.queryForObject("SELECT COUNT(*) FROM app.documents WHERE id = ?", Long.class, id);
            if (count == null || count == 0L) return id;
        }
        return DocumentPolicies.newDocumentId();
    }

    private String documentSelect() {
        return """
                SELECT d.id, d.case_id, d.filename, d.content_type, d.size, d.role, d.parse_task_id, d.created_at,
                       COALESCE(t.status, d.parse_status) AS parse_status
                FROM app.documents d
                LEFT JOIN app.tasks t ON t.id = d.parse_task_id
                """;
    }

    private DocumentView map(ResultSet rs, int ignored) throws SQLException {
        return new DocumentView(
                rs.getString("id"),
                rs.getString("case_id"),
                rs.getString("filename"),
                rs.getString("content_type"),
                rs.getLong("size"),
                rs.getString("role"),
                rs.getString("parse_status"),
                rs.getObject("parse_task_id", UUID.class),
                rs.getObject("created_at", OffsetDateTime.class));
    }
}
