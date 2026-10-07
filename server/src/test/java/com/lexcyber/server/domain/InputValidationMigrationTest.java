package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.PostgreSQLContainer;

/** V24 -> V25 invalidates v2 artifacts without a verified input proof. */
class InputValidationMigrationTest {
    @Test
    void invalidatesMalformedInputProofsAndRegisteredDescendants() {
        Assumptions.assumeTrue(dockerAvailable(), "migration test requires Docker");
        try (PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber_input_validation_migration")
                .withUsername("lex_app").withPassword("lex_app")) {
            postgres.start();
            DataSource dataSource = new DriverManagerDataSource(
                    postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
            Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").target("24").load().migrate();
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            Flyway flyway = Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").load();
            UUID owner = UUID.randomUUID();
            account(jdbc, owner);

            String[] bad = {
                    "{}",
                    "{\"input_validation\":null}",
                    "{\"input_validation\":{\"schema_version\":\"wrong\",\"status\":\"verified\",\"checks\":[],\"blockers\":[]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"blocked\",\"checks\":[],\"blockers\":[{}]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[],\"blockers\":[{}]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":{},\"blockers\":[]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":null,\"blockers\":[]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[null],\"blockers\":[]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[{\"status\":\"blocked\"}],\"blockers\":[]}}",
                    "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[],\"blockers\":null}}"
            };
            Artifact[] malformed = new Artifact[bad.length];
            Artifact[] descendants = new Artifact[2];
            for (int i = 0; i < bad.length; i++) {
                UUID caseId = caseRow(jdbc, owner);
                Artifact root = module(jdbc, caseId, "compliance", "case.compliance.v2", bad[i], true);
                malformed[i] = root;
                if (i == 0) {
                    Artifact child = module(jdbc, caseId, "sentencing", "sentencing.v2", valid(), true);
                    Artifact draft = draft(jdbc, caseId, owner, valid(), true);
                    descendants[0] = child;
                    descendants[1] = draft;
                    dependency(jdbc, child.version(), root.version());
                    dependency(jdbc, draft.version(), child.version());
                    assertEquals(root.version(), confirmed(jdbc, root.stream()));
                    assertEquals(child.version(), confirmed(jdbc, child.stream()));
                    assertEquals(draft.version(), approved(jdbc, draft.head()));
                }
            }
            UUID validCase = caseRow(jdbc, owner);
            Artifact valid = module(jdbc, validCase, "compliance", "case.compliance.v2", valid(), true);
            UUID legacyCase = caseRow(jdbc, owner);
            Artifact legacy = module(jdbc, legacyCase, "compliance", "case.module.v1", "{}", true);

            flyway.migrate();

            // All malformed forms are invalidated, including direct and recursive descendants.
            for (Artifact root : malformed) {
                assertEquals("dependency_changed", jdbc.queryForObject(
                        "SELECT stale_reason FROM app.module_head WHERE artifact_stream_id = ?", String.class, root.stream()));
            }
            assertEquals("dependency_changed", jdbc.queryForObject(
                    "SELECT stale_reason FROM app.module_head WHERE artifact_stream_id = ?", String.class, descendants[0].stream()));
            assertEquals("dependency_changed", jdbc.queryForObject(
                    "SELECT stale_reason FROM app.draft_head WHERE draft_id = ?", String.class, descendants[1].head()));
            assertEquals(false, jdbc.queryForObject("SELECT stale FROM app.module_head WHERE artifact_stream_id = ?",
                    Boolean.class, valid.stream()));
            assertEquals(false, jdbc.queryForObject("SELECT stale FROM app.module_head WHERE artifact_stream_id = ?",
                    Boolean.class, legacy.stream()));
            assertEquals(valid.version(), latest(jdbc, valid.stream()));
            assertEquals(valid.version(), confirmed(jdbc, valid.stream()));
            assertEquals(valid(), jdbc.queryForObject("SELECT payload::text FROM app.artifact_version WHERE artifact_version_id = ?",
                    String.class, valid.version()).replace(" ", ""));
        }
    }

    private String valid() {
        return "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[],\"blockers\":[]}}";
    }

    private Artifact module(JdbcTemplate jdbc, UUID caseId, String module, String schema, String payload, boolean head) {
        UUID stream = UUID.randomUUID(), version = UUID.randomUUID();
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version) VALUES (?, ?, ?, ?, 2)",
                stream, caseId, module, "module:" + module);
        version(jdbc, stream, version, schema, payload);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?", version, stream);
        if (head) jdbc.update("INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale) VALUES (?, ?, ?, ?, false)",
                caseId, module, stream, version);
        return new Artifact(stream, version, null);
    }

    private Artifact draft(JdbcTemplate jdbc, UUID caseId, UUID owner, String payload, boolean head) {
        UUID draft = UUID.randomUUID(), stream = UUID.randomUUID(), version = UUID.randomUUID();
        jdbc.update("INSERT INTO app.case_drafts(id, case_id, draft_type, render_doc_type, updated_by) VALUES (?, ?, 'judgment', 'judgment', ?)", draft, caseId, owner);
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version) VALUES (?, ?, 'draft', ?, 2)", stream, caseId, "draft:" + draft);
        version(jdbc, stream, version, "draft.v2", payload);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?", version, stream);
        if (head) jdbc.update("INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale) VALUES (?, ?, ?, ?, false)", draft, caseId, stream, version);
        return new Artifact(stream, version, draft);
    }

    private void version(JdbcTemplate jdbc, UUID stream, UUID version, String schema, String payload) {
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, schema_version, outcome_status, payload, dependency_snapshot, output_hash) VALUES (?, ?, 1, ?, 'calculated', ?::jsonb, '{\"as_of_date\":\"2026-01-01\"}', 'migration')", version, stream, schema, payload);
    }
    private void dependency(JdbcTemplate jdbc, UUID child, UUID parent) { jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?)", child, parent); }
    private void account(JdbcTemplate jdbc, UUID id) { jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) VALUES (?, ?, ?, 'Migration', 'hash')", id, "input_" + id, "input_" + id); }
    private UUID caseRow(JdbcTemplate jdbc, UUID owner) { UUID id = UUID.randomUUID(); jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json) VALUES (?, ?, ?, 'CN', '2026-01-01', '{}'::jsonb)", id, owner, "input-" + id); return id; }
    private UUID latest(JdbcTemplate jdbc, UUID stream) { return jdbc.queryForObject("SELECT latest_version_id FROM app.artifact_stream WHERE artifact_stream_id = ?", UUID.class, stream); }
    private UUID confirmed(JdbcTemplate jdbc, UUID stream) { return jdbc.queryForObject("SELECT confirmed_version_id FROM app.module_head WHERE artifact_stream_id = ?", UUID.class, stream); }
    private UUID approved(JdbcTemplate jdbc, UUID draft) { return jdbc.queryForObject("SELECT approved_version_id FROM app.draft_head WHERE draft_id = ?", UUID.class, draft); }
    private boolean dockerAvailable() { try { return DockerClientFactory.instance().isDockerAvailable(); } catch (RuntimeException unavailable) { return false; } }
    private record Artifact(UUID stream, UUID version, UUID head) {}
}
