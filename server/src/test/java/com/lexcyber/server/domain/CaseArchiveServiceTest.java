package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
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
        UUID facts = UUID.randomUUID();
        jdbc.update("INSERT INTO app.facts_head(case_id) VALUES (?::uuid)", caseId);
        jdbc.update("""
                INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash, payload, created_by,
                                               confirmed_by, confirmed_at)
                VALUES (?, ?::uuid, 1, 'facts', '{}'::jsonb, ?, ?, now())
                """, facts, caseId, account, account);
        jdbc.update("UPDATE app.facts_head SET confirmed_facts_version_id = ? WHERE case_id = ?::uuid", facts, caseId);

        Map<String, Object> first = archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account);
        Map<String, Object> second = archives.create(caseId, CaseArchiveService.PROFILE_CASE_FULL, account);
        assertEquals(facts, first.get("factsVersionId"));
        assertEquals(first.get("manifestHash"), second.get("manifestHash"));
        assertEquals(1, first.get("archiveVersion"));
        assertEquals(2, second.get("archiveVersion"));
        assertEquals(2, jdbc.queryForObject("SELECT COUNT(*) FROM app.case_archive WHERE case_id = ?::uuid", Integer.class, caseId));
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
