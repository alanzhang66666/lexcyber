package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;

/** Date binding checks shared by v2 module confirmation and draft approval. */
class LegalAnalysisContextTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private JdbcTemplate jdbc;
    private UUID account;
    private UUID caseId;

    @BeforeAll
    static void openDatabase() {
        if (EXTERNAL_JDBC == null || EXTERNAL_JDBC.isBlank()) {
            postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                    .withDatabaseName("lexcyber")
                    .withUsername("lex_app")
                    .withPassword("lex_app");
            postgres.start();
        }
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
        account = UUID.randomUUID();
        caseId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                VALUES (?, ?, ?, 'Date test', 'hash')
                """, account, "date_" + account, "date_" + account);
    }

    @Test
    void confirmationRejectsV2ArtifactWhenCaseDateIsMissing() {
        insertCase(null);
        UUID version = insertModuleArtifact("case.compliance.v2", "2026-09-06");
        insertModuleHead("compliance", version);

        ApiException error = assertThrows(ApiException.class,
                () -> new ModuleConfirmationService(jdbc).confirm(caseId.toString(), "compliance", account));

        assertEquals("DEPENDENCY_STALE", error.code());
    }

    @Test
    void approvalRejectsLateV2CompletionWithOldFrozenDate() {
        insertCase("2026-09-07");
        UUID draftId = UUID.randomUUID();
        UUID streamId = UUID.randomUUID();
        UUID version = UUID.randomUUID();
        jdbc.update("INSERT INTO app.case_drafts(id, case_id, draft_type, updated_by) VALUES (?, ?, 'judgment', ?)",
                draftId, caseId, account);
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                VALUES (?, ?, 'draft', ?, 2)
                """, streamId, caseId, "draft:" + draftId);
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, 'draft.v2', 'calculated', '{}',
                        '{"as_of_date":"2026-09-06","artifacts":[]}', 'late')
                """, version, streamId);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                version, streamId);
        jdbc.update("""
                INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale)
                VALUES (?, ?, ?, NULL, false)
                """, draftId, caseId, streamId);

        ApiException error = assertThrows(ApiException.class,
                () -> new DraftApprovalService(jdbc).approve(caseId.toString(), draftId, account));

        assertEquals("DEPENDENCY_STALE", error.code());
    }

    private void insertCase(String asOfDate) {
        jdbc.update("""
                INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json)
                VALUES (?, ?, 'Date test', 'CN', ?::date, '{}'::jsonb)
                """, caseId, account, asOfDate);
    }

    private UUID insertModuleArtifact(String schemaVersion, String asOfDate) {
        UUID streamId = UUID.randomUUID();
        UUID version = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                VALUES (?, ?, 'compliance', 'module:compliance', 2)
                """, streamId, caseId);
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, ?, 'calculated', '{}', jsonb_build_object('as_of_date', ?), 'module')
                """, version, streamId, schemaVersion, asOfDate);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                version, streamId);
        return version;
    }

    private void insertModuleHead(String module, UUID version) {
        UUID streamId = jdbc.queryForObject(
                "SELECT artifact_stream_id FROM app.artifact_version WHERE artifact_version_id = ?",
                UUID.class, version);
        jdbc.update("""
                INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale)
                VALUES (?, ?, ?, NULL, false)
                """, caseId, module, streamId);
    }

    private DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) {
            source.setUrl(EXTERNAL_JDBC);
            source.setUsername(envOr("TEST_JDBC_USER", "lex_app"));
            source.setPassword(envOr("TEST_JDBC_PASSWORD", "lex_app"));
        } else {
            source.setUrl(postgres.getJdbcUrl());
            source.setUsername(postgres.getUsername());
            source.setPassword(postgres.getPassword());
        }
        return source;
    }

    private static String envOr(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
