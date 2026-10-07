package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * v1.3 §4.8.6 — 案件级归档。锁序：cases FOR UPDATE → facts_head FOR SHARE → 各 head FOR SHARE，
 * 锁持有到 manifest 落库，杜绝「检查时有效、落库时已失效」的混合 manifest。
 * 版本号经 cases.next_archive_version 分配（ADR-0006）。
 */
@Service
public class CaseArchiveService {
    public static final String PROFILE_CASE_FULL = "case.full.v1";

    private final JdbcTemplate jdbc;

    public CaseArchiveService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Gap(String code, String detail) {
    }

    /** 归档前置评估：返回可定位缺口；空列表 = 可归档。 */
    public List<Gap> evaluate(String caseId, String profile) {
        List<Gap> gaps = new ArrayList<>();
        List<Boolean> factsRows = jdbc.query("""
                SELECT confirmed_facts_version_id IS NOT NULL
                FROM app.facts_head WHERE case_id = ?::uuid
                """, (rs, ignored) -> rs.getBoolean(1), caseId);
        if (factsRows.isEmpty() || !factsRows.get(0)) {
            gaps.add(new Gap("facts_not_confirmed", "事实基线未确认"));
        }
        // case.full.v1 requires every module, including a confirmed not_applicable
        // compliance artifact, and an approved draft.
        for (String module : List.of("compliance", "conviction", "sentencing")) {
            List<String> confirmed = jdbc.query("""
                    SELECT module FROM app.module_head
                    WHERE case_id = ?::uuid AND module = ?
                      AND confirmed_version_id IS NOT NULL AND NOT stale
                    """, (rs, ignored) -> rs.getString(1), caseId, module);
            if (confirmed.isEmpty()) {
                gaps.add(new Gap("module_not_confirmed", module));
            }
        }
        List<String> draftGaps = jdbc.query("""
                SELECT dh.draft_id::text FROM app.draft_head dh
                WHERE dh.case_id = ?::uuid
                  AND NOT (dh.approved_version_id IS NOT NULL AND NOT dh.stale)
                """, (rs, ignored) -> rs.getString(1), caseId);
        if (draftGaps.isEmpty()) {
            boolean hasDraft = Boolean.TRUE.equals(jdbc.queryForObject("""
                    SELECT EXISTS (SELECT 1 FROM app.draft_head WHERE case_id = ?::uuid)
                    """, Boolean.class, caseId));
            if (!hasDraft) {
                gaps.add(new Gap("draft_not_approved", "draft"));
            }
        } else {
            draftGaps.forEach(draft -> gaps.add(new Gap("draft_not_approved", draft)));
        }
        return gaps;
    }

    @Transactional
    public Map<String, Object> create(String caseId, String profile, UUID createdBy) {
        if (!PROFILE_CASE_FULL.equals(profile)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_ARCHIVE_PROFILE",
                    "不支持的归档 profile");
        }
        jdbc.queryForObject("SELECT id FROM app.cases WHERE id = ?::uuid FOR UPDATE",
                String.class, caseId);
        // §4.8.6 steps 3-4：head 行 SHARE 锁，持有到 COMMIT
        List<Map<String, Object>> heads = jdbc.queryForList("""
                SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?::uuid FOR SHARE
                """, caseId);
        jdbc.queryForList(
                "SELECT module, confirmed_version_id FROM app.module_head WHERE case_id = ?::uuid FOR SHARE",
                caseId);
        jdbc.queryForList(
                "SELECT draft_id, approved_version_id FROM app.draft_head WHERE case_id = ?::uuid FOR SHARE",
                caseId);

        List<Gap> gaps = evaluate(caseId, profile);
        if (!gaps.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "ARCHIVE_PRECONDITION_FAILED",
                    "归档前置不满足", Map.of("gaps", gaps));
        }
        UUID factsVersionId = heads.isEmpty() ? null
                : (UUID) heads.get(0).get("confirmed_facts_version_id");

        // 固化清单：confirmed module versions + approved draft versions + 相关 parse versions
        List<Map<String, Object>> items = new ArrayList<>();
        jdbc.query("""
                SELECT confirmed_version_id, module FROM app.module_head
                WHERE case_id = ?::uuid AND confirmed_version_id IS NOT NULL
                """, (rs, ignored) -> items.add(Map.of(
                "artifact_version_id", rs.getString(1), "role", rs.getString(2))), caseId);
        jdbc.query("""
                SELECT approved_version_id FROM app.draft_head
                WHERE case_id = ?::uuid AND approved_version_id IS NOT NULL
                """, (rs, ignored) -> items.add(Map.of(
                "artifact_version_id", rs.getString(1), "role", "draft")), caseId);
        jdbc.query("""
                SELECT v.artifact_version_id FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                WHERE s.case_id = ?::uuid AND s.kind = 'parse'
                  AND v.artifact_version_id = s.latest_version_id
                """, (rs, ignored) -> items.add(Map.of(
                "artifact_version_id", rs.getString(1), "role", "parse")), caseId);

        // Return a stable item order on both creation and idempotent replay.
        items.sort(Comparator.comparing((Map<String, Object> item) -> String.valueOf(item.get("role")))
                .thenComparing(item -> String.valueOf(item.get("artifact_version_id"))));

        // 同案校验（§4.6.11：FK 表达不了，领域服务在事务内校验）
        for (Map<String, Object> item : items) {
            Long sameCase = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM app.artifact_version v
                    JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                    WHERE v.artifact_version_id = ?::uuid AND s.case_id = ?::uuid
                    """, Long.class, item.get("artifact_version_id"), caseId);
            if (sameCase == null || sameCase == 0L) {
                throw new ApiException(HttpStatus.CONFLICT, "ARCHIVE_ITEM_CROSS_CASE",
                        "归档清单包含跨案件工件，已阻断");
            }
        }

        // canonicalize → manifest_hash
        List<String> sorted = items.stream()
                .map(i -> i.get("artifact_version_id") + ":" + i.get("role"))
                .sorted().toList();
        String manifestHash = FactsBaselineService.sha256(
                caseId + "|" + factsVersionId + "|" + String.join(";", sorted));

        // The case row lock serializes this lookup with insertion. A retry for an
        // identical frozen state returns the immutable archive and does not consume
        // another archive version.
        List<Map<String, Object>> existingRows = jdbc.queryForList("""
                SELECT archive_id, case_id, archive_version, archive_profile,
                       facts_version_id, manifest_hash, created_at
                FROM app.case_archive
                WHERE case_id = ?::uuid AND manifest_hash = ?
                """, caseId, manifestHash);
        if (!existingRows.isEmpty()) {
            Map<String, Object> existing = existingRows.get(0);
            existing.put("created_at", jdbc.queryForObject("""
                    SELECT created_at FROM app.case_archive WHERE archive_id = ?
                    """, (rs, ignored) -> rs.getObject("created_at", OffsetDateTime.class),
                    existing.get("archive_id")));
            List<Map<String, Object>> existingItems = jdbc.queryForList("""
                    SELECT artifact_version_id, role
                    FROM app.case_archive_item
                    WHERE archive_id = ?
                    ORDER BY role, artifact_version_id
                    """, existing.get("archive_id"));
            return archiveResponse(existing, existingItems);
        }

        Integer archiveVersion = jdbc.queryForObject(
                "SELECT next_archive_version FROM app.cases WHERE id = ?::uuid",
                Integer.class, caseId);
        UUID archiveId = UUID.randomUUID();
        OffsetDateTime createdAt = jdbc.queryForObject("""
                INSERT INTO app.case_archive(
                    archive_id, case_id, archive_version, archive_profile,
                    facts_version_id, manifest_hash, created_by)
                VALUES (?, ?::uuid, ?, ?, ?, ?, ?)
                RETURNING created_at
                """, OffsetDateTime.class, archiveId, caseId, archiveVersion, profile,
                factsVersionId, manifestHash, createdBy);
        for (Map<String, Object> item : items) {
            jdbc.update("""
                    INSERT INTO app.case_archive_item(archive_id, artifact_version_id, role)
                    VALUES (?, ?::uuid, ?)
                    """, archiveId, item.get("artifact_version_id"), item.get("role"));
        }
        jdbc.update(
                "UPDATE app.cases SET next_archive_version = next_archive_version + 1 WHERE id = ?::uuid",
                caseId);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("archiveId", archiveId);
        result.put("caseId", caseId);
        result.put("archiveVersion", archiveVersion);
        result.put("archiveProfile", profile);
        result.put("factsVersionId", factsVersionId);
        result.put("manifestHash", manifestHash);
        result.put("createdAt", createdAt);
        result.put("items", items.stream().map(item -> Map.of(
                "artifactVersionId", item.get("artifact_version_id"),
                "role", item.get("role"))).toList());
        return result;
    }

    private Map<String, Object> archiveResponse(Map<String, Object> archive,
                                                 List<Map<String, Object>> items) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("archiveId", archive.get("archive_id"));
        result.put("caseId", String.valueOf(archive.get("case_id")));
        result.put("archiveVersion", archive.get("archive_version"));
        result.put("archiveProfile", archive.get("archive_profile"));
        result.put("factsVersionId", archive.get("facts_version_id"));
        result.put("manifestHash", archive.get("manifest_hash"));
        result.put("createdAt", archive.get("created_at"));
        result.put("items", items.stream().map(item -> Map.of(
                "artifactVersionId", String.valueOf(item.get("artifact_version_id")),
                "role", item.get("role"))).toList());
        return result;
    }
}
