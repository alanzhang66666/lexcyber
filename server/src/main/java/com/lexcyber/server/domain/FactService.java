package com.lexcyber.server.domain;

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

/**
 * /v1 事实端点的适配层（契约冻结，语义映射到新模型）：
 * - items 读写落在可编辑实体表 app.case_fact；
 * - status 由 facts_head 派生（ADR-0002）：head.confirmed 存在 → confirmed，否则 draft；
 * - confirm 走 FactsBaselineService：固化 draft 版本 → 确认 → 推进 head；
 * - /v1 保持旧语义：confirmed 后 PUT/confirm 返 409（新版本能力只在 /v2 暴露）。
 */
@Service
public class FactService {
    public static final String SCHEMA_VERSION = "case.facts.v1";
    private final JdbcTemplate jdbc;
    private final CaseService cases;
    private final FactsBaselineService baseline;

    public FactService(JdbcTemplate jdbc, CaseService cases, FactsBaselineService baseline) {
        this.jdbc = jdbc;
        this.cases = cases;
        this.baseline = baseline;
    }

    @Transactional(readOnly = true)
    public FactView get(UUID ownerAccountId, String caseId) {
        caseId = cases.requireOwned(ownerAccountId, caseId).id();
        return view(caseId);
    }

    @Transactional
    public FactView replace(UUID ownerAccountId, String caseId, FactUpdate update) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        if (confirmed(caseId)) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_CONFIRMED", "已确认的事实不能再修改");
        }
        List<FactItem> items = normalize(update == null ? null : update.items());
        jdbc.update("DELETE FROM app.case_fact WHERE case_id = ?::uuid", caseId);
        for (FactItem item : items) {
            jdbc.update("""
                    INSERT INTO app.case_fact(
                        case_id, external_id, fact_key, fact_value, locator,
                        source_document_id, verification_status, source_version)
                    VALUES (?::uuid, ?, ?, ?, ?, ?::uuid, ?, ?)
                    """, caseId, item.id(), item.key(), item.value(), item.locator(),
                    resolveDocumentId(item.sourceDocumentId()),
                    item.verificationStatus(), item.sourceVersion());
        }
        jdbc.update("""
                INSERT INTO app.facts_head(case_id, updated_at) VALUES (?::uuid, now())
                ON CONFLICT (case_id) DO UPDATE SET updated_at = now()
                """, caseId);
        return view(caseId);
    }

    @Transactional
    public FactView confirm(UUID ownerAccountId, String caseId) {
        caseId = cases.lockOwned(ownerAccountId, caseId).id();
        if (confirmed(caseId)) {
            throw new ApiException(HttpStatus.CONFLICT, "FACTS_CONFIRMED", "事实已确认");
        }
        UUID versionId = baseline.createDraftVersion(caseId, ownerAccountId);
        baseline.confirm(caseId, versionId, null, ownerAccountId);
        return view(caseId);
    }

    private boolean confirmed(String caseId) {
        return baseline.confirmedVersionId(caseId).isPresent();
    }

    /** items 读自编辑实体表；sourceDocumentId 以 uuid 返回（新模型身份）。 */
    private FactView view(String caseId) {
        List<FactItem> items = jdbc.query("""
                SELECT external_id, fact_id, fact_key, fact_value, locator,
                       source_document_id, verification_status, source_version
                FROM app.case_fact WHERE case_id = ?::uuid
                ORDER BY created_at, fact_id
                """, this::mapItem, caseId);
        List<Map<String, Object>> head = jdbc.queryForList("""
                SELECT h.confirmed_facts_version_id, h.updated_at, v.confirmed_at
                FROM app.facts_head h
                LEFT JOIN app.facts_version v ON v.facts_version_id = h.confirmed_facts_version_id
                WHERE h.case_id = ?::uuid
                """, caseId);
        String status = "draft";
        OffsetDateTime updatedAt = OffsetDateTime.now();
        OffsetDateTime confirmedAt = null;
        if (!head.isEmpty()) {
            updatedAt = toOffset(head.get(0).get("updated_at"));
            confirmedAt = toOffset(head.get(0).get("confirmed_at"));
            if (head.get(0).get("confirmed_facts_version_id") != null) {
                status = "confirmed";
            }
        }
        return new FactView(caseId, SCHEMA_VERSION, status, items, updatedAt, confirmedAt);
    }

    /** queryForList 对 timestamptz 返回 java.sql.Timestamp；统一换算为 UTC OffsetDateTime。 */
    private static OffsetDateTime toOffset(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof OffsetDateTime odt) {
            return odt;
        }
        if (value instanceof java.sql.Timestamp ts) {
            return ts.toInstant().atOffset(java.time.ZoneOffset.UTC);
        }
        throw new IllegalStateException("unexpected temporal type: " + value.getClass());
    }

    private FactItem mapItem(ResultSet rs, int ignored) throws SQLException {
        String external = rs.getString("external_id");
        Object factId = rs.getObject("fact_id");
        Object docId = rs.getObject("source_document_id");
        return new FactItem(
                external != null ? external : String.valueOf(factId),
                rs.getString("fact_key"),
                rs.getString("fact_value"),
                rs.getString("locator"),
                docId == null ? null : docId.toString(),
                rs.getString("verification_status"),
                rs.getString("source_version"));
    }

    /**
     * sourceDocumentId 解析：uuid 直接透传；旧 doc-xxxx 经 legacy_id_map；
     * 解析不到置 NULL（v1 契约允许自由形 id，降级为无引用而非拒绝写入）。
     */
    private String resolveDocumentId(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String value = raw.trim();
        if (IdentityService.isUuid(value)) {
            return value;
        }
        List<String> rows = jdbc.query(
                "SELECT uuid_id::text FROM app.legacy_id_map WHERE legacy_id = ? AND entity_kind = 'document'",
                (rs, ignored) -> rs.getString(1), value);
        return rows.isEmpty() ? null : rows.get(0);
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
            normalized.add(new FactItem(
                    id,
                    item.key().trim(),
                    item.value(),
                    item.locator(),
                    item.sourceDocumentId(),
                    requireVerification(item.verificationStatus()),
                    blankToNull(item.sourceVersion())));
        }
        return List.copyOf(normalized);
    }

    private static String requireVerification(String status) {
        if (status == null || status.isBlank()) {
            return null;
        }
        String value = status.trim();
        if (!ModulePolicies.VERIFICATION.contains(value)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "unsupported verificationStatus");
        }
        return value;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
