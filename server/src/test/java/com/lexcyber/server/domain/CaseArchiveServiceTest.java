package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.lexcyber.server.api.ApiException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;

/** PostgreSQL regression coverage for case-level archive preconditions and manifests. */
class CaseArchiveServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;
    private JdbcTemplate jdbc;
    private CaseArchiveService archives;
    private UUID account;
    private String caseId;

    @BeforeAll
    static void openDatabase() {
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) return;
        postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber")
                .withUsername("lex_app")
                .withPassword("lex_app");
        postgres.start();
    }

    @AfterAll
    static void closeDatabase() {
        if (postgres != null) postgres.stop();
    }

    @BeforeEach
    void setup() {
        DataSource dataSource = dataSource();
        Flyway.configure().dataSource(dataSource).schemas("app")
                .locations("classpath:db/migration/app").load().migrate();
        jdbc = new JdbcTemplate(dataSource);
        archives = new CaseArchiveService(jdbc);
        account = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """, account, "archive_" + account, account.toString(), "Archive", "hash");
        caseId = UUID.randomUUID().toString();
        jdbc.update("""
                INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, metadata_json)
                VALUES (?::uuid, ?, 'archive case', 'CN', '{}'::jsonb)
                """, caseId, account);
    }

    @Test
    void emptyCaseReturnsFactsGapWithoutCreatingArchive() {
        ApiException error = assertThrows(ApiException.class,
                () -> archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account));
        assertEquals(HttpStatus.CONFLICT, error.status());
        assertEquals("ARCHIVE_PRECONDITION_FAILED", error.code());
        @SuppressWarnings("unchecked")
        java.util.List<CaseArchiveService.Gap> gaps =
                (java.util.List<CaseArchiveService.Gap>) error.details().get("gaps");
        assertEquals("facts_not_confirmed", gaps.get(0).code());
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.case_archive WHERE case_id = ?::uuid", Integer.class, caseId));
        assertEquals(1, jdbc.queryForObject("SELECT next_archive_version FROM app.cases WHERE id = ?::uuid", Integer.class, caseId));
    }

    @Test
    void confirmedFactsCreatesStableManifest() {
        UUID facts = seedFacts(1, "facts");
        seedModule("compliance");
        seedModule("conviction");
        seedModule("sentencing");
        seedDraft();

        Map<String, Object> first = archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account);
        Map<String, Object> second = archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account);
        assertEquals(facts, first.get("factsVersionId"));
        assertEquals(first.get("archiveId"), second.get("archiveId"));
        assertEquals(first.get("manifestHash"), second.get("manifestHash"));
        assertEquals(first.get("createdAt"), second.get("createdAt"));
        assertEquals(first.get("items"), second.get("items"));
        assertEquals(1, first.get("archiveVersion"));
        assertEquals(1, second.get("archiveVersion"));
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM app.case_archive WHERE case_id = ?::uuid", Integer.class, caseId));
        assertEquals(2, jdbc.queryForObject("SELECT next_archive_version FROM app.cases WHERE id = ?::uuid", Integer.class, caseId));

        UUID nextFacts = seedFacts(2, "facts-2");
        jdbc.update("UPDATE app.facts_head SET confirmed_facts_version_id = ? WHERE case_id = ?::uuid", nextFacts, caseId);
        Map<String, Object> third = archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account);
        assertEquals(nextFacts, third.get("factsVersionId"));
        assertEquals(2, third.get("archiveVersion"));
        assertTrue(!first.get("manifestHash").equals(third.get("manifestHash")));
        assertEquals(2, jdbc.queryForObject("SELECT COUNT(*) FROM app.case_archive WHERE case_id = ?::uuid", Integer.class, caseId));
    }

    @Test
    void missingRequiredModuleReturns定位Gap() {
        seedFacts(1, "facts");
        seedModule("compliance");
        seedModule("sentencing");
        seedDraft();
        ApiException error = assertThrows(ApiException.class,
                () -> archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account));
        @SuppressWarnings("unchecked")
        List<CaseArchiveService.Gap> gaps = (List<CaseArchiveService.Gap>) error.details().get("gaps");
        assertTrue(gaps.stream().anyMatch(g -> g.code().equals("module_not_confirmed") && g.detail().equals("conviction")));
    }

    @Test
    void missingApprovedDraftReturns定位Gap() {
        seedFacts(1, "facts");
        seedModule("compliance");
        seedModule("conviction");
        seedModule("sentencing");
        ApiException error = assertThrows(ApiException.class,
                () -> archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account));
        @SuppressWarnings("unchecked")
        List<CaseArchiveService.Gap> gaps = (List<CaseArchiveService.Gap>) error.details().get("gaps");
        assertTrue(gaps.stream().anyMatch(g -> g.code().equals("draft_not_approved")));
    }

    @Test
    void staleApprovedDraftStillBlocksWhenAnotherDraftIsValid() {
        seedFacts(1, "facts");
        seedModule("compliance");
        seedModule("conviction");
        seedModule("sentencing");
        seedDraft();
        seedDraft(true);
        ApiException error = assertThrows(ApiException.class,
                () -> archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account));
        @SuppressWarnings("unchecked")
        List<CaseArchiveService.Gap> gaps = (List<CaseArchiveService.Gap>) error.details().get("gaps");
        assertTrue(gaps.stream().anyMatch(g -> g.code().equals("draft_not_approved")));
    }

    private UUID seedFacts(int version, String hash) {
        UUID facts = UUID.randomUUID();
        jdbc.update("INSERT INTO app.facts_head(case_id) VALUES (?::uuid) ON CONFLICT DO NOTHING", caseId);
        jdbc.update("""
                INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash, payload, created_by,
                                               confirmed_by, confirmed_at)
                VALUES (?, ?::uuid, ?, ?, '{}'::jsonb, ?, ?, now())
                """, facts, caseId, version, hash, account, account);
        jdbc.update("UPDATE app.facts_head SET confirmed_facts_version_id = ? WHERE case_id = ?::uuid", facts, caseId);
        return facts;
    }

    private UUID seedModule(String module) {
        UUID stream = UUID.randomUUID();
        UUID artifact = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key)
                VALUES (?, ?::uuid, ?, ?)
                """, stream, caseId, module, "module:" + module);
        jdbc.update("""
                INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version,
                    schema_version, outcome_status, payload, blockers, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, 'case.module.v1', 'calculated', '{}'::jsonb, '[]'::jsonb, '{}'::jsonb, ?)
                """, artifact, stream, module + "-hash");
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ?, next_version = 2 WHERE artifact_stream_id = ?", artifact, stream);
        jdbc.update("""
                INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale)
                VALUES (?::uuid, ?, ?, ?, false)
                """, caseId, module, stream, artifact);
        return artifact;
    }

    private UUID seedDraft() {
        return seedDraft(false);
    }

    private UUID seedDraft(boolean stale) {
        UUID draft = UUID.randomUUID();
        UUID stream = UUID.randomUUID();
        UUID artifact = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.case_drafts(id, case_id, draft_type, updated_by)
                VALUES (?, ?::uuid, 'draft', ?)
                """, draft, caseId, account);
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key)
                VALUES (?, ?::uuid, 'draft', ?)
                """, stream, caseId, "draft:" + draft);
        jdbc.update("""
                INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version,
                    schema_version, outcome_status, payload, blockers, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, 'draft.v1', 'calculated', '{}'::jsonb, '[]'::jsonb, '{}'::jsonb, 'draft-hash')
                """, artifact, stream);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ?, next_version = 2 WHERE artifact_stream_id = ?", artifact, stream);
        jdbc.update("""
                INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale, stale_reason)
                VALUES (?, ?::uuid, ?, ?, ?, ?)
                """, draft, caseId, stream, artifact, stale,
                stale ? "newer_version_published" : null);
        return artifact;
    }

    @Test
    void unknownProfileIsRejectedClearly() {
        ApiException error = assertThrows(ApiException.class,
                () -> archives.create(caseId, "case.unknown.v1", account));
        assertEquals(HttpStatus.BAD_REQUEST, error.status());
        assertEquals("INVALID_ARCHIVE_PROFILE", error.code());
    }

    private DataSource dataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) {
            dataSource.setUrl(EXTERNAL_JDBC);
            dataSource.setUsername(envOr("TEST_JDBC_USER", "lex_app"));
            dataSource.setPassword(envOr("TEST_JDBC_PASSWORD", "lex_app"));
        } else {
            dataSource.setUrl(postgres.getJdbcUrl());
            dataSource.setUsername(postgres.getUsername());
            dataSource.setPassword(postgres.getPassword());
        }
        return dataSource;
    }

    private static String envOr(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
