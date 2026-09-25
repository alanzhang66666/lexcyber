package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DraftService {
    private final JdbcTemplate jdbc;
    private final CaseService cases;

    public DraftService(JdbcTemplate jdbc, CaseService cases) {
        this.jdbc = jdbc;
        this.cases = cases;
    }

    @Transactional
    public DraftView create(UUID ownerAccountId, String caseId, DraftCreate request) {
        cases.lockOwned(ownerAccountId, caseId);
        String draftType = request.draftType().trim();
        String body = request.body() == null ? "" : request.body();
        String id = DocumentPolicies.newDraftId();
        jdbc.update("""
                INSERT INTO app.case_drafts(id, case_id, draft_type, body, version, updated_by, updated_at,
                                            template_version, source_version)
                VALUES (?, ?, ?, ?, 1, ?, now(), ?, ?)
                """, id, caseId, draftType, body, ownerAccountId,
                blankToNull(request.templateVersion()), blankToNull(request.sourceVersion()));
        return requireOwned(ownerAccountId, caseId, id);
    }

    @Transactional(readOnly = true)
    public DraftList list(UUID ownerAccountId, String caseId) {
        cases.requireOwned(ownerAccountId, caseId);
        List<DraftView> items = jdbc.query(
                selectSql() + " WHERE case_id = ? ORDER BY updated_at DESC, id",
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
        if (update.version() != current.version()) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_VERSION_CONFLICT", "草稿版本已变更");
        }
        String templateVersion = update.templateVersion() == null
                ? current.templateVersion() : blankToNull(update.templateVersion());
        String sourceVersion = update.sourceVersion() == null
                ? current.sourceVersion() : blankToNull(update.sourceVersion());
        int changed = jdbc.update("""
                UPDATE app.case_drafts
                SET body = ?, version = version + 1, updated_by = ?, updated_at = now(),
                    template_version = ?, source_version = ?
                WHERE id = ? AND case_id = ? AND version = ?
                """, update.body(), ownerAccountId, templateVersion, sourceVersion, draftId, caseId, update.version());
        if (changed == 0) {
            throw new ApiException(HttpStatus.CONFLICT, "DRAFT_VERSION_CONFLICT", "草稿版本已变更");
        }
        jdbc.update("""
                UPDATE app.review_records
                SET status = 'superseded'
                WHERE draft_id = ? AND draft_version = ? AND status IN ('pending', 'approved')
                """, draftId, current.version());
        return requireOwned(ownerAccountId, caseId, draftId);
    }

    private DraftView requireOwned(UUID ownerAccountId, String caseId, String draftId) {
        cases.requireOwned(ownerAccountId, caseId);
        List<DraftView> rows = jdbc.query(selectSql() + " WHERE id = ? AND case_id = ?", this::map, draftId, caseId);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "DRAFT_NOT_FOUND", "草稿不存在或不可访问");
        }
        return rows.get(0);
    }

    private String selectSql() {
        return """
                SELECT id, case_id, draft_type, body, version, updated_by, updated_at,
                       template_version, source_version
                FROM app.case_drafts
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
