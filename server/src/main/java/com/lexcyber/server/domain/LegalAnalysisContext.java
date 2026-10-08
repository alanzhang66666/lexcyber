package com.lexcyber.server.domain;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;

/** Date is part of a legal execution's frozen inputs, alongside facts and upstream artifacts. */
public final class LegalAnalysisContext {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final List<String> V2_SCHEMAS = List.of(
            "case.compliance.v2", "case.conviction.v2", "sentencing.v2", "draft.v2");

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
        requireVerifiedInputValidation(jdbc, caseId, artifactVersionId);
        // A previously confirmed baseline may contain dangling references from
        // older collection replacements. Validate its frozen payload, not the
        // present working copy, before any result is approved again.
        FactsBaselineService baseline = new FactsBaselineService(jdbc, new StalePropagationService(jdbc));
        for (UUID factsVersionId : jdbc.query("""
                SELECT facts_version_id FROM app.artifact_facts_dependency
                WHERE artifact_version_id = ?
                """, (rs, ignored) -> rs.getObject(1, UUID.class), artifactVersionId)) {
            baseline.validateVersionReferences(caseId, factsVersionId);
        }
    }

    /**
     * v2 results are executable only when the payload carries the proof that
     * the inputs actually read by the engine were verified.  Walk the frozen
     * artifact dependency graph as well: a new downstream result cannot hide
     * an old or malformed v2 upstream result.
     */
    private static void requireVerifiedInputValidation(JdbcTemplate jdbc, String caseId, UUID artifactVersionId) {
        List<MapRow> artifacts = jdbc.query("""
                WITH RECURSIVE upstream(artifact_version_id) AS (
                    SELECT ?::uuid
                    UNION
                    SELECT d.depends_on_artifact_version_id
                    FROM app.artifact_artifact_dependency d
                    JOIN upstream u ON u.artifact_version_id = d.artifact_version_id
                )
                SELECT v.schema_version, v.payload::text, s.case_id
                FROM upstream u
                JOIN app.artifact_version v ON v.artifact_version_id = u.artifact_version_id
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                """, (rs, ignored) -> new MapRow(rs.getString(1), rs.getString(2), rs.getObject(3, UUID.class)),
                artifactVersionId);
        if (artifacts.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "v2 工件不存在或依赖闭包无法解析，确认或批准被阻断");
        }
        for (MapRow artifact : artifacts) {
            if (!caseId.equals(artifact.caseId().toString())) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                        "工件依赖跨越案件边界，确认或批准被阻断");
            }
            if (!V2_SCHEMAS.contains(artifact.schema())) {
                continue;
            }
            if (!hasVerifiedInputValidation(artifact.schema(), artifact.payload())) {
                throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                        "v2 工件缺少有效的输入校验证明，确认或批准被阻断");
            }
        }
    }

    private static boolean hasVerifiedInputValidation(String schema, String payload) {
        try {
            JsonNode root = JSON.readTree(payload);
            if (root == null || !root.isObject()) {
                return false;
            }
            JsonNode marker = root.get("input_validation");
            String expected = switch (schema) {
                case "case.compliance.v2" -> "case.input-validation.v1";
                case "case.conviction.v2" -> "case.input-validation.v1";
                case "sentencing.v2" -> "case.input-validation.v1";
                case "draft.v2" -> "case.input-validation.v1";
                default -> null;
            };
            if (expected == null || marker == null || !marker.isObject()
                    || !expected.equals(marker.path("schema_version").asText(null))
                    || !"verified".equals(marker.path("status").asText(null))) {
                return false;
            }
            JsonNode checks = marker.get("checks");
            JsonNode blockers = marker.get("blockers");
            if (checks == null || !checks.isArray() || blockers == null || !blockers.isArray()
                    || !blockers.isEmpty()) {
                return false;
            }
            for (JsonNode check : checks) {
                if (!check.isObject() || !"verified".equals(check.path("status").asText(null))) {
                    return false;
                }
            }
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    private record MapRow(String schema, String payload, UUID caseId) {}
}
