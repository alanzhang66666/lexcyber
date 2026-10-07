package com.lexcyber.server.domain;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.DraftExportEngineClient;
import com.lexcyber.server.storage.ObjectStorage;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Exports one immutable draft artifact without changing any lifecycle pointer. */
@Service
public class DraftExportService {
    private static final String DOCX_MIME =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private final JdbcTemplate jdbc;
    private final CaseService cases;
    private final ObjectMapper objectMapper;
    private final DraftExportEngineClient engine;
    private final ObjectStorage storage;

    public DraftExportService(JdbcTemplate jdbc, CaseService cases, ObjectMapper objectMapper,
                              DraftExportEngineClient engine, ObjectStorage storage) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.objectMapper = objectMapper;
        this.engine = engine;
        this.storage = storage;
    }

    @Transactional(readOnly = true)
    public ExportedDocx export(UUID ownerAccountId, String caseId, UUID artifactVersionId) {
        String ownedCaseId = cases.requireOwned(ownerAccountId, caseId).id();
        ExportRow row = jdbc.query("""
                SELECT v.artifact_version_id, v.version, v.schema_version, v.outcome_status,
                       v.payload::text AS payload, v.blockers::text AS blockers, v.created_at, s.case_id, s.kind,
                       fd.facts_version_id
                FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                JOIN app.cases c ON c.id = s.case_id AND c.owner_account_id = ?
                LEFT JOIN app.artifact_facts_dependency fd
                    ON fd.artifact_version_id = v.artifact_version_id
                WHERE v.artifact_version_id = ? AND s.case_id = ?::uuid
                """, (rs, rowNum) -> mapRow(rs), ownerAccountId, artifactVersionId, ownedCaseId)
                .stream().findFirst().orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND, "ARTIFACT_NOT_FOUND", "工件版本不存在或不可访问"));

        if (!"draft".equals(row.kind())) {
            throw blocked("只有文书草稿工件可以导出");
        }
        if (!List.of("draft.v2", "case.draft.v1").contains(row.schemaVersion())
                || !"calculated".equals(row.outcomeStatus())) {
            throw blocked("该文书版本不支持导出");
        }
        Map<String, Object> artifact;
        try {
            artifact = objectMapper.readValue(row.payload(), new TypeReference<>() {});
        } catch (Exception ex) {
            throw blocked("文书工件正文格式无效");
        }
        String body = text(artifact.get("body"));
        Object unresolved = artifact.get("unresolved");
        if ("blocked".equals(artifact.get("status")) || blockersPresent(row.blockers())
                || body == null || body.isBlank()
                || unresolved != null && (!(unresolved instanceof List<?> list) || !list.isEmpty())
                || containsPlaceholder(body)) {
            throw blocked("文书正文存在未解决内容，暂不可导出");
        }
        String docType = "case.draft.v1".equals(row.schemaVersion())
                ? text(artifact.get("draft_type")) : text(artifact.get("doc_type"));
        if (docType == null || docType.isBlank()) {
            throw blocked("文书类型缺失");
        }
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("case_id", row.caseId().toString());
        request.put("artifact_version_id", row.artifactVersionId().toString());
        request.put("version", row.version());
        request.put("schema_version", row.schemaVersion());
        request.put("doc_type", docType);
        request.put("body", body);
        request.put("created_at", row.createdAt().toString());
        request.put("facts_version_id", row.factsVersionId() == null ? null : row.factsVersionId().toString());
        byte[] rendered = engine.render(request);
        String hash = sha256(rendered);
        String key = "exports/draft/" + row.artifactVersionId() + "/" + hash + ".docx";
        storage.put(key, rendered, DOCX_MIME);
        byte[] persisted = storage.get(key);
        if (persisted == null || !Arrays.equals(rendered, persisted) || !hash.equals(sha256(persisted))) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DRAFT_EXPORT_STORAGE_FAILED",
                    "导出文件存储校验失败");
        }
        String filename = safeFilename(docType) + "-v" + row.version() + "-"
                + row.artifactVersionId().toString().substring(0, 8) + ".docx";
        return new ExportedDocx(persisted, filename, hash, row.artifactVersionId(), row.version());
    }

    private ExportRow mapRow(ResultSet rs) throws SQLException {
        return new ExportRow(rs.getObject("artifact_version_id", UUID.class),
                rs.getInt("version"), rs.getString("schema_version"), rs.getString("outcome_status"),
                rs.getString("payload"), rs.getString("blockers"), rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("case_id", UUID.class), rs.getString("kind"),
                rs.getObject("facts_version_id", UUID.class));
    }

    private static boolean containsPlaceholder(String body) {
        return body.matches("(?s).*\\{\\{\\s*[^{}]+?\\s*\\}\\}.*")
                || body.matches("(?s).*【[^】]*】.*");
    }

    private static String text(Object value) {
        return value instanceof String string ? string : null;
    }

    private boolean blockersPresent(String blockers) {
        if (blockers == null || blockers.isBlank() || "[]".equals(blockers.trim())) return false;
        try {
            List<?> values = objectMapper.readValue(blockers, new TypeReference<>() {});
            return !values.isEmpty();
        } catch (Exception ex) {
            return true;
        }
    }

    private static ApiException blocked(String message) {
        return new ApiException(HttpStatus.CONFLICT, "DRAFT_EXPORT_BLOCKED", message);
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder out = new StringBuilder(64);
            for (byte value : digest) out.append(String.format("%02x", value));
            return out.toString();
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static String safeFilename(String value) {
        String safe = value.replaceAll("[\\p{Cntrl}\\\\/:*?\"<>|]+", "_").trim();
        return safe.isBlank() ? "draft" : safe.substring(0, Math.min(safe.length(), 80));
    }

    public record ExportedDocx(byte[] bytes, String filename, String sha256,
                               UUID artifactVersionId, int version) {}

    private record ExportRow(UUID artifactVersionId, int version, String schemaVersion,
                             String outcomeStatus, String payload, String blockers, OffsetDateTime createdAt,
                             UUID caseId, String kind, UUID factsVersionId) {}
}
