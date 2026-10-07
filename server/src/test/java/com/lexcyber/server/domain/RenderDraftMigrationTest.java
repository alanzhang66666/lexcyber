package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.PostgreSQLContainer;

/** V20 -> V21 migration coverage for pre-UUID rendered draft streams. */
class RenderDraftMigrationTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");

    @Test
    void migratesLegacyRenderedDraftToUuidDescriptorAndIsIdempotent() {
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
                    .locations("classpath:db/migration/app").target("20").load().migrate();
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);

            UUID owner = UUID.randomUUID();
            UUID caseId = UUID.randomUUID();
            UUID streamId = UUID.randomUUID();
            UUID versionId = UUID.randomUUID();
            UUID reviewId = UUID.randomUUID();
            String payload = "{\"body\":\"legacy indictment\",\"docType\":\"indictment\"}";
            jdbc.update("""
                    INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                    VALUES (?, ?, ?, ?, ?)
                    """, owner, "migration_" + owner, "migration_" + owner, "migration", "hash");
            jdbc.update("""
                    INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, metadata_json)
                    VALUES (?, ?, 'legacy migration case', 'CN', '{}'::jsonb)
                    """, caseId, owner);
            jdbc.update("""
                    INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                    VALUES (?, ?, 'draft', 'draft:indictment', 2)
                    """, streamId, caseId);
            jdbc.update("""
                    INSERT INTO app.artifact_version(
                        artifact_version_id, artifact_stream_id, version, schema_version,
                        outcome_status, payload, dependency_snapshot, output_hash)
                    VALUES (?, ?, 1, 'draft.v1', 'calculated', ?::jsonb, '{}'::jsonb, 'legacy-hash')
                    """, versionId, streamId, payload);
            jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                    versionId, streamId);
            jdbc.update("""
                    INSERT INTO app.review_records(review_id, artifact_version_id, case_id, status, actor_id)
                    VALUES (?, ?, ?, 'pending', ?)
                    """, reviewId, versionId, caseId, owner);

            Flyway flyway = Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").load();
            flyway.migrate();

            assertEquals(streamId, jdbc.queryForObject(
                    "SELECT artifact_stream_id FROM app.artifact_stream WHERE artifact_stream_id = ?",
                    UUID.class, streamId));
            assertEquals(versionId, jdbc.queryForObject(
                    "SELECT latest_version_id FROM app.artifact_stream WHERE artifact_stream_id = ?",
                    UUID.class, streamId));
            assertEquals(1, jdbc.queryForObject(
                    "SELECT version FROM app.artifact_version WHERE artifact_version_id = ?",
                    Integer.class, versionId));
            assertEquals(Boolean.TRUE, jdbc.queryForObject(
                    "SELECT payload = ?::jsonb FROM app.artifact_version WHERE artifact_version_id = ?",
                    Boolean.class, payload, versionId));
            String migratedScope = jdbc.queryForObject(
                    "SELECT scope_key FROM app.artifact_stream WHERE artifact_stream_id = ?",
                    String.class, streamId);
            assertTrue(migratedScope.startsWith("draft:"));
            UUID descriptorId = UUID.fromString(migratedScope.substring("draft:".length()));
            assertNotNull(jdbc.queryForObject(
                    "SELECT id FROM app.case_drafts WHERE id = ? AND case_id = ? AND render_doc_type = ?",
                    UUID.class, descriptorId, caseId, "indictment"));
            assertEquals(streamId, jdbc.queryForObject(
                    "SELECT artifact_stream_id FROM app.draft_head WHERE draft_id = ?",
                    UUID.class, descriptorId));
            assertEquals("superseded", jdbc.queryForObject(
                    "SELECT status FROM app.review_records WHERE review_id = ?", String.class, reviewId));

            flyway.validate();
            flyway.migrate();
            assertEquals(1, jdbc.queryForObject(
                    "SELECT COUNT(*) FROM app.case_drafts WHERE case_id = ? AND render_doc_type = ?",
                    Integer.class, caseId, "indictment"));
            assertEquals(1, jdbc.queryForObject(
                    "SELECT COUNT(*) FROM app.draft_head WHERE draft_id = ? AND artifact_stream_id = ?",
                    Integer.class, descriptorId, streamId));
            assertEquals(migratedScope, jdbc.queryForObject(
                    "SELECT scope_key FROM app.artifact_stream WHERE artifact_stream_id = ?",
                    String.class, streamId));
        }
    }

    private boolean dockerAvailable() {
        try {
            return DockerClientFactory.instance().isDockerAvailable();
        } catch (RuntimeException unavailable) {
            return false;
        }
    }
}
