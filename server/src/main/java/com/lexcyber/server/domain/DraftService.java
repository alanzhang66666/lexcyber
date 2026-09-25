package com.lexcyber.server.domain;

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

/**
 * /v1 文书端点适配层：
 * - case_drafts 仅作描述符（draft_type/template_version/…）；正文在 artifact_version.payload.body；
 * - 版本号 = draft stream 的 artifact version；批准状态在 draft_head（INV-DRAFT-HEAD-001）；
 * - replace/create 走手工发布（execution_id = NULL），不直接改历史版本。
 */
@Service
public class DraftService {
    private final JdbcTemplate jdbc;
    private final CaseService cases;
    private final IdentityService ids;
    private final ArtifactPublicationService artifacts;

    public DraftService(JdbcTemplate jdbc, CaseService cases, ArtifactPublicationService artifacts) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.artifacts = artifacts;
        this.ids = new IdentityService(jdbc);
    }

    @Transactional
    public DraftView create(UUID ownerAccountId, String caseId, DraftCreate request) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        String draftType = request.draftType().trim();
        String body = request.body() == null ? "" : request.body();
        String id = DocumentPolicies.newDraftId();
        jdbc.update("""
                INSERT INTO app.case_drafts(id, case_id, draft_type, updated_by, updated_at,
                                            template_version, source_version)
                VALUES (?::uuid, ?::uuid, ?, ?, now(), ?, ?)
                """, id, caseId, draftType, ownerAccountId,
                blankToNull(request.templateVersion()), blankToNull(request.sourceVersion()));
        ensureStreamAndHead(caseId, id);
        artifacts.publish(new ArtifactPublicationService.PublishRequest(
                caseId, "draft", "draft:" + id, "case.draft.v1", "calculated",
                draftPayload(draftType, body, request.templateVersion(), request.sourceVersion()),
                null, "{}", baselineConfirmed(caseId), List.of(), List.of(), null, null, null));
        return requireOwned(ownerAccountId, caseId, id);
    }

    @Transactional(readOnly = true)
    public DraftList list(UUID ownerAccountId, String caseId) {
        cases.requireOwned(ownerAccountId, caseId);
        List<DraftView> items = jdbc.query(
                selectSql() + " WHERE d.case_id = ?::uuid ORDER BY d.updated_at DESC, d.id",
                this::map, caseId);
        return new DraftList(items);
    }

    @Transactional(readOnly = true)
    public DraftView get(UUID ownerAccountId, String caseId, String draftId) {
        return requireOwned(ownerAccountId, caseId, draftId);
    }

    @Transactional
    public DraftView replace(UUID ownerAccountId, String caseId, String draftId, DraftUpdate update) {
        cases.lockOwned(ownerAccountId, caseId);
        DraftView current = requireOwned(ownerAccountId, caseId, draftId);
        caseId = current.caseId();
        draftId = current.id();
        if (update.version() != current.version()) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_VERSION_CONFLICT", "草稿版本已变更");
        }
        String templateVersion = update.templateVersion() == null
                ? current.templateVersion() : blankToNull(update.templateVersion());
        String sourceVersion = update.sourceVersion() == null
                ? current.sourceVersion() : blankToNull(update.sourceVersion());
        jdbc.update("""
                UPDATE app.case_drafts
                SET updated_by = ?, updated_at = now(), template_version = ?, source_version = ?
                WHERE id = ?::uuid AND case_id = ?::uuid
                """, ownerAccountId, templateVersion, sourceVersion, draftId, caseId);
        artifacts.publish(new ArtifactPublicationService.PublishRequest(
                caseId, "draft", "draft:" + draftId, "case.draft.v1", "calculated",
                draftPayload(current.draftType(), update.body(), templateVersion, sourceVersion),
                null, "{}", baselineConfirmed(caseId), List.of(), List.of(), null, null, null));
        return requireOwned(ownerAccountId, caseId, draftId);
    }

    private UUID ensureStreamAndHead(String caseId, String draftId) {
        UUID streamId = artifacts.ensureStreamLocked(caseId, "draft", "draft:" + draftId);
        jdbc.update("""
                INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id)
                VALUES (?::uuid, ?::uuid, ?)
                ON CONFLICT (draft_id) DO NOTHING
                """, draftId, caseId, streamId);
        return streamId;
    }

    private UUID baselineConfirmed(String caseId) {
        return jdbc.query(
                "SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?::uuid",
                (rs, ignored) -> rs.getObject(1, UUID.class), caseId)
                .stream().filter(java.util.Objects::nonNull).findFirst().orElse(null);
    }

    private String draftPayload(String draftType, String body, String templateVersion, String sourceVersion) {
        StringBuilder json = new StringBuilder("{\"draft_type\":");
        json.append(quote(draftType)).append(",\"body\":").append(quote(body));
        json.append(",\"template_version\":").append(quote(templateVersion));
        json.append(",\"source_version\":").append(quote(sourceVersion)).append('}');
        return json.toString();
    }

    private static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toCharArray()) {
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> out.append(c);
            }
        }
        return out.append('"').toString();
    }

    private DraftView requireOwned(UUID ownerAccountId, String caseId, String draftId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        List<DraftView> rows = jdbc.query(selectSql() + " WHERE d.id = ?::uuid AND d.case_id = ?::uuid",
                this::map, ids.draftId(draftId), caseId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DRAFT_NOT_FOUND", "草稿不存在或不可访问");
        }
        return rows.get(0);
    }

    private String selectSql() {
        return """
                SELECT d.id, d.case_id, d.draft_type, d.updated_by, d.updated_at,
                       d.template_version, d.source_version,
                       COALESCE(v.payload ->> 'body', '') AS body,
                       COALESCE(v.version, 0) AS version
                FROM app.case_drafts d
                LEFT JOIN app.draft_head h ON h.draft_id = d.id
                LEFT JOIN app.artifact_stream s ON s.artifact_stream_id = h.artifact_stream_id
                LEFT JOIN app.artifact_version v ON v.artifact_version_id = s.latest_version_id
                """;
    }

    private DraftView map(ResultSet rs, int ignored) throws SQLException {
        return new DraftView(
                rs.getString("id"),
                rs.getString("case_id"),
                rs.getString("draft_type"),
                rs.getString("body"),
                rs.getInt("version"),
                rs.getObject("updated_by", UUID.class),
                rs.getObject("updated_at", OffsetDateTime.class),
                rs.getString("template_version"),
                rs.getString("source_version"));
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }
}
