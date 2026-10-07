package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;

/** Date is part of a legal execution's frozen inputs, alongside facts and upstream artifacts. */
public final class LegalAnalysisContext {
    private LegalAnalysisContext() {}

    public static void lockCase(JdbcTemplate jdbc, String caseId) {
        jdbc.queryForList("SELECT id FROM app.cases WHERE id = ?::uuid FOR SHARE", caseId);
    }

    public static void requireCurrent(JdbcTemplate jdbc, String caseId, UUID artifactVersionId) {
        Long invalid = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                JOIN app.cases c ON c.id = s.case_id
                WHERE v.artifact_version_id = ? AND c.id = ?::uuid
                  AND v.schema_version IN ('case.compliance.v2', 'case.conviction.v2', 'sentencing.v2', 'draft.v2')
                  AND (c.as_of_date IS NULL OR
                       v.dependency_snapshot ->> 'as_of_date' IS DISTINCT FROM to_char(c.as_of_date, 'YYYY-MM-DD'))
                """, Long.class, artifactVersionId, caseId);
        if (invalid != null && invalid > 0L) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "结果基准日期缺失或已变更，请按当前基准日期重新执行");
        }
    }
}
