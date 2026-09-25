package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * 解析公开 API 入口处的实体标识。
 *
 * v13 起 cases / documents / case_drafts 主键为 uuid；历史 TEXT id
 * （case-…/doc-…/draft-…）经 app.legacy_id_map 兼容解析，保证已发出的旧链接仍可访问。
 * 解析结果返回规范 uuid 文本（小写），调用方在 SQL 中以 ?::uuid 绑定。
 */
@Service
public class IdentityService {
    private final JdbcTemplate jdbc;

    public IdentityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String caseId(String raw) {
        return resolve(raw, "case", "CASE_NOT_FOUND", "案件不存在或不可访问");
    }

    /** tasks.case_id 可空：空输入返回 null，非空必须可解析。 */
    public String caseIdOrNull(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        return caseId(raw);
    }

    public String documentId(String raw) {
        return resolve(raw, "document", "DOCUMENT_NOT_FOUND", "材料不存在或不可访问");
    }

    public String documentIdOrNull(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        return documentId(raw);
    }

    public String draftId(String raw) {
        return resolve(raw, "draft", "DRAFT_NOT_FOUND", "草稿不存在或不可访问");
    }

    private String resolve(String raw, String kind, String code, String message) {
        if (raw == null || raw.isBlank()) {
            throw new ApiException(HttpStatus.NOT_FOUND, code, message);
        }
        String value = raw.trim();
        if (isUuid(value)) {
            return value.toLowerCase(java.util.Locale.ROOT);
        }
        List<String> rows = jdbc.query(
                "SELECT uuid_id::text FROM app.legacy_id_map WHERE legacy_id = ? AND entity_kind = ?",
                (rs, ignored) -> rs.getString(1), value, kind);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, code, message);
        }
        return rows.get(0);
    }

    public static boolean isUuid(String value) {
        try {
            UUID.fromString(value);
            return true;
        } catch (RuntimeException ex) {
            return false;
        }
    }
}
