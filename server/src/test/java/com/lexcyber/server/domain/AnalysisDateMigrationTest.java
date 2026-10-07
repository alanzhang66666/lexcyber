package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.PostgreSQLContainer;

/** V21 -> V22 regression coverage for populated analysis-date heads. */
class AnalysisDateMigrationTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");

    @Test
    void invalidatesOnlyUnboundV2HeadsAndPreservesHistoryAndPointers() {
        Assumptions.assumeTrue(EXTERNAL_JDBC == null || EXTERNAL_JDBC.isBlank(),
                "migration test owns a disposable Postgres container; TEST_JDBC_URL is not used");
        Assumptions.assumeTrue(dockerAvailable(),
                "migration test requires Docker; CI is expected to provide Docker");

        try (PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber_migration")
                .withUsername("lex_app")
                .withPassword("lex_app")) {
            postgres.start();
            DataSource dataSource = new DriverManagerDataSource(
                    postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
            Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").target("21").load().migrate();
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            Flyway flyway = Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").load();

            UUID owner = UUID.randomUUID();
            insertAccount(jdbc, owner);
            UUID matchingCase = insertCase(jdbc, owner, "2026-09-06");
            UUID missingCase = insertCase(jdbc, owner, null);
            UUID unboundCase = insertCase(jdbc, owner, "2026-09-06");
            UUID mismatchedCase = insertCase(jdbc, owner, "2026-09-07");
            UUID legacyCase = insertCase(jdbc, owner, "2026-09-07");

            Head matchingModule = insertModule(jdbc, matchingCase, "case.compliance.v2", "2026-09-06");
            Head missingModule = insertModule(jdbc, missingCase, "case.compliance.v2", null);
            Head unboundModule = insertModule(jdbc, unboundCase, "case.compliance.v2", null);
            Head mismatchedModule = insertModule(jdbc, mismatchedCase, "case.compliance.v2", "2026-09-06");
            Head legacyModule = insertModule(jdbc, legacyCase, "case.compliance.v1", null);
            Head matchingDraft = insertDraft(jdbc, matchingCase, owner, "draft.v2", "2026-09-06");
            Head missingDraft = insertDraft(jdbc, missingCase, owner, "draft.v2", null);
            Head unboundDraft = insertDraft(jdbc, unboundCase, owner, "draft.v2", null);
            Head mismatchedDraft = insertDraft(jdbc, mismatchedCase, owner, "draft.v2", "2026-09-06");
            Head legacyDraft = insertDraft(jdbc, legacyCase, owner, "draft.v1", null);

            flyway.migrate(); // V22 invalidates unbound v2 heads.

            assertHead(jdbc, "module_head", matchingModule, false, null);
            assertHead(jdbc, "module_head", missingModule, true, "analysis_date_unbound");
            assertHead(jdbc, "module_head", unboundModule, true, "analysis_date_unbound");
            assertHead(jdbc, "module_head", mismatchedModule, true, "analysis_date_unbound");
            assertHead(jdbc, "module_head", legacyModule, false, null);
            assertHead(jdbc, "draft_head", matchingDraft, false, null);
            assertHead(jdbc, "draft_head", missingDraft, true, "analysis_date_unbound");
            assertHead(jdbc, "draft_head", unboundDraft, true, "analysis_date_unbound");
            assertHead(jdbc, "draft_head", mismatchedDraft, true, "analysis_date_unbound");
            assertHead(jdbc, "draft_head", legacyDraft, false, null);

            assertEquals(matchingModule.versionId(), latest(jdbc, matchingModule.streamId()));
            assertEquals(missingModule.versionId(), confirmed(jdbc, missingModule.streamId()));
            assertEquals(mismatchedModule.versionId(), confirmed(jdbc, mismatchedModule.streamId()));
            assertEquals(mismatchedDraft.versionId(), approved(jdbc, mismatchedDraft.headId()));
            assertPayload(jdbc, mismatchedModule.versionId(), "{\"module\":\"frozen\"}");
            assertPayload(jdbc, mismatchedDraft.versionId(), "{\"body\":\"frozen\"}");
            assertEquals(1, jdbc.queryForObject(
                    "SELECT COUNT(*) FROM app.artifact_version WHERE artifact_version_id = ?",
                    Integer.class, mismatchedDraft.versionId()));

            jdbc.update("UPDATE app.module_head SET stale = true, stale_reason = 'analysis_date_changed' "
                    + "WHERE case_id = ? AND module = 'compliance'", matchingCase);
            jdbc.update("UPDATE app.draft_head SET stale = true, stale_reason = 'analysis_date_changed' "
                    + "WHERE draft_id = ?", matchingDraft.headId());
            assertThrows(DataIntegrityViolationException.class, () -> jdbc.update(
                    "UPDATE app.module_head SET stale = true, stale_reason = 'unknown_reason' WHERE case_id = ? "
                            + "AND module = 'compliance'", legacyCase));
            assertThrows(DataIntegrityViolationException.class, () -> jdbc.update(
                    "UPDATE app.draft_head SET stale = true, stale_reason = 'unknown_reason' WHERE draft_id = ?",
                    legacyDraft.headId()));
            assertEquals("analysis_date_changed", jdbc.queryForObject(
                    "SELECT stale_reason FROM app.module_head WHERE case_id = ? AND module = 'compliance'",
                    String.class, matchingCase));
        }
    }

    private Head insertModule(JdbcTemplate jdbc, UUID caseId, String schema, String asOfDate) {
        UUID streamId = UUID.randomUUID();
        UUID versionId = UUID.randomUUID();
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version) "
                + "VALUES (?, ?, 'compliance', 'module:compliance', 2)", streamId, caseId);
        insertVersion(jdbc, streamId, versionId, schema, asOfDate, "{\"module\":\"frozen\"}");
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                versionId, streamId);
        jdbc.update("INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale) "
                + "VALUES (?, 'compliance', ?, ?, false)", caseId, streamId, versionId);
        return new Head(streamId, versionId, null);
    }

    private Head insertDraft(JdbcTemplate jdbc, UUID caseId, UUID owner, String schema, String asOfDate) {
        UUID draftId = UUID.randomUUID();
        UUID streamId = UUID.randomUUID();
        UUID versionId = UUID.randomUUID();
        jdbc.update("INSERT INTO app.case_drafts(id, case_id, draft_type, render_doc_type, updated_by) "
                + "VALUES (?, ?, 'judgment', 'judgment-' || ?::text, ?)", draftId, caseId, draftId, owner);
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version) "
                + "VALUES (?, ?, 'draft', ?, 2)", streamId, caseId, "draft:" + draftId);
        insertVersion(jdbc, streamId, versionId, schema, asOfDate, "{\"body\":\"frozen\"}");
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                versionId, streamId);
        jdbc.update("INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale) "
                + "VALUES (?, ?, ?, ?, false)", draftId, caseId, streamId, versionId);
        return new Head(streamId, versionId, draftId);
    }

    private void insertVersion(JdbcTemplate jdbc, UUID streamId, UUID versionId, String schema,
            String asOfDate, String payload) {
        String dependency = asOfDate == null ? "{}" : "{\"as_of_date\":\"" + asOfDate + "\"}";
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, "
                + "schema_version, outcome_status, payload, dependency_snapshot, output_hash) "
                + "VALUES (?, ?, 1, ?, 'calculated', ?::jsonb, ?::jsonb, 'frozen')",
                versionId, streamId, schema, payload, dependency);
    }

    private UUID insertCase(JdbcTemplate jdbc, UUID owner, String asOfDate) {
        UUID caseId = UUID.randomUUID();
        jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json) "
                + "VALUES (?, ?, 'migration case', 'CN', ?::date, '{}'::jsonb)", caseId, owner, asOfDate);
        return caseId;
    }

    private void insertAccount(JdbcTemplate jdbc, UUID owner) {
        jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) "
                + "VALUES (?, ?, ?, 'Migration', 'hash')", owner, "migration_" + owner, "migration_" + owner);
    }

    private void assertHead(JdbcTemplate jdbc, String table, Head head, boolean stale, String reason) {
        assertEquals(stale, jdbc.queryForObject("SELECT stale FROM app." + table + " WHERE "
                + (table.equals("module_head") ? "artifact_stream_id = ?" : "draft_id = ?"),
                Boolean.class, table.equals("module_head") ? head.streamId() : head.headId()));
        assertEquals(reason, jdbc.queryForObject("SELECT stale_reason FROM app." + table + " WHERE "
                + (table.equals("module_head") ? "artifact_stream_id = ?" : "draft_id = ?"),
                String.class, table.equals("module_head") ? head.streamId() : head.headId()));
    }

    private UUID latest(JdbcTemplate jdbc, UUID streamId) {
        return jdbc.queryForObject("SELECT latest_version_id FROM app.artifact_stream WHERE artifact_stream_id = ?",
                UUID.class, streamId);
    }

    private UUID approved(JdbcTemplate jdbc, UUID draftId) {
        return jdbc.queryForObject("SELECT approved_version_id FROM app.draft_head WHERE draft_id = ?",
                UUID.class, draftId);
    }

    private UUID confirmed(JdbcTemplate jdbc, UUID streamId) {
        return jdbc.queryForObject("SELECT confirmed_version_id FROM app.module_head WHERE artifact_stream_id = ?",
                UUID.class, streamId);
    }

    private void assertPayload(JdbcTemplate jdbc, UUID versionId, String expectedJson) {
        assertEquals(Boolean.TRUE, jdbc.queryForObject(
                "SELECT payload = ?::jsonb FROM app.artifact_version WHERE artifact_version_id = ?",
                Boolean.class, expectedJson, versionId));
    }

    private boolean dockerAvailable() {
        try {
            return DockerClientFactory.instance().isDockerAvailable();
        } catch (RuntimeException unavailable) {
            return false;
        }
    }

    private record Head(UUID streamId, UUID versionId, UUID headId) {}
}
