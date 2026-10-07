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

/** Real V23 -> V24 upgrade, retaining immutable snapshots and head pointers. */
class FactsReferenceMigrationTest {
    @Test
    void invalidatesBrokenFrozenReferencesAndDescendantsWithoutUsingWorkingCopy() {
        Assumptions.assumeTrue(dockerAvailable(), "migration test requires Docker; CI provides Docker");
        try (PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber_reference_migration")
                .withUsername("lex_app").withPassword("lex_app")) {
            postgres.start();
            DataSource dataSource = new DriverManagerDataSource(
                    postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
            Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").target("23").load().migrate();
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            UUID owner = UUID.randomUUID();
            insertAccount(jdbc, owner);

            UUID brokenCase = insertCase(jdbc, owner);
            String brokenPayload = "{\"items\":[{\"key\":\"k\",\"evidenceIds\":[\"live-proof\"]}],"
                    + "\"entities\":{\"evidence\":[]}}";
            UUID brokenFacts = insertFacts(jdbc, brokenCase, owner, brokenPayload);
            jdbc.update("INSERT INTO app.case_evidence(case_id, external_id, evidence_type) VALUES (?, 'live-proof', 'document')",
                    brokenCase); // Presence in today's working copy must not repair frozen history.
            Artifact module = insertModule(jdbc, brokenCase, "compliance", "case.compliance.v2", "{}");
            Artifact sentencing = insertModule(jdbc, brokenCase, "sentencing", "sentencing.v2", "{}");
            Artifact draft = insertDraft(jdbc, brokenCase, owner, "{}");
            bindFacts(jdbc, module.versionId(), brokenFacts);
            dependency(jdbc, sentencing.versionId(), module.versionId());
            dependency(jdbc, draft.versionId(), sentencing.versionId());

            for (String invalidPayload : new String[] {
                    "{\"items\":[],\"entities\":{\"evidence\":{}}}",
                    "{\"items\":[{\"actorId\":\"absent-actor\"}],\"entities\":{\"actors\":[]}}",
                    "{\"items\":[{\"evidenceIds\":\"not-an-array\"}],\"entities\":{}}",
                    "{\"items\":[{\"evidenceIds\":[\"ambiguous\"]}],\"entities\":{\"evidence\":["
                            + "{\"entityId\":\"" + UUID.randomUUID() + "\",\"id\":\"ambiguous\"},"
                            + "{\"entityId\":\"" + UUID.randomUUID() + "\",\"id\":\"ambiguous\"}]}}"
            }) {
                UUID invalidCase = insertCase(jdbc, owner);
                UUID facts = insertFacts(jdbc, invalidCase, owner, invalidPayload);
                Artifact result = insertModule(jdbc, invalidCase, "conviction", "case.conviction.v2", "{}");
                bindFacts(jdbc, result.versionId(), facts);
            }

            UUID validCase = insertCase(jdbc, owner);
            UUID archivedProof = UUID.randomUUID();
            UUID archivedActor = UUID.randomUUID();
            String validPayload = "{\"items\":[{\"evidenceIds\":[\"archived-proof\"],\"actorId\":\"archived-actor\"}],"
                    + "\"entities\":{\"evidence\":[{\"entityId\":\"" + archivedProof
                    + "\",\"id\":\"archived-proof\"}],\"actors\":[{\"entityId\":\"" + archivedActor
                    + "\",\"externalId\":\"archived-actor\"}]}}";
            UUID validFacts = insertFacts(jdbc, validCase, owner, validPayload);
            Artifact valid = insertModule(jdbc, validCase, "conviction", "case.conviction.v2", "{}");
            bindFacts(jdbc, valid.versionId(), validFacts);
            Artifact legacy = insertModule(jdbc, validCase, "compliance", "case.module.v1", "{}");
            UUID emptyFacts = UUID.randomUUID();
            jdbc.update("INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash, payload, created_by) "
                    + "VALUES (?, ?, 2, 'legacy-empty', '{}', ?)", emptyFacts, validCase, owner);
            bindFacts(jdbc, legacy.versionId(), emptyFacts);

            Flyway.configure().dataSource(dataSource).schemas("app")
                    .locations("classpath:db/migration/app").load().migrate();

            assertHead(jdbc, "module_head", module.streamId(), true, "dependency_changed");
            assertHead(jdbc, "module_head", sentencing.streamId(), true, "dependency_changed");
            assertHead(jdbc, "draft_head", draft.headId(), true, "dependency_changed");
            assertHead(jdbc, "module_head", valid.streamId(), false, null);
            assertHead(jdbc, "module_head", legacy.streamId(), false, null);
            assertEquals(6, jdbc.queryForObject("SELECT COUNT(*) FROM app.module_head WHERE stale AND stale_reason = 'dependency_changed'",
                    Integer.class));
            assertEquals(module.versionId(), confirmed(jdbc, module.streamId()));
            assertEquals(module.versionId(), latest(jdbc, module.streamId()));
            assertEquals(sentencing.versionId(), confirmed(jdbc, sentencing.streamId()));
            assertEquals(draft.versionId(), approved(jdbc, draft.headId()));
            assertEquals(brokenFacts, jdbc.queryForObject("SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?",
                    UUID.class, brokenCase));
            assertEquals(Boolean.TRUE, jdbc.queryForObject("SELECT payload = ?::jsonb FROM app.facts_version WHERE facts_version_id = ?",
                    Boolean.class, brokenPayload, brokenFacts));
            assertEquals(Boolean.TRUE, jdbc.queryForObject("SELECT payload = ?::jsonb FROM app.facts_version WHERE facts_version_id = ?",
                    Boolean.class, validPayload, validFacts));
            assertPayload(jdbc, module.versionId(), "{}");
            assertPayload(jdbc, sentencing.versionId(), "{}");
            assertPayload(jdbc, draft.versionId(), "{}");
        }
    }

    private UUID insertFacts(JdbcTemplate jdbc, UUID caseId, UUID owner, String payload) {
        UUID facts = UUID.randomUUID();
        jdbc.update("INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash, payload, created_by, confirmed_by, confirmed_at) "
                + "VALUES (?, ?, 1, 'frozen-reference', ?::jsonb, ?, ?, now())", facts, caseId, payload, owner, owner);
        jdbc.update("INSERT INTO app.facts_head(case_id, confirmed_facts_version_id, next_version) VALUES (?, ?, 2)", caseId, facts);
        return facts;
    }

    private void bindFacts(JdbcTemplate jdbc, UUID artifact, UUID facts) {
        jdbc.update("INSERT INTO app.artifact_facts_dependency(artifact_version_id, facts_version_id) VALUES (?, ?)", artifact, facts);
    }

    private Artifact insertModule(JdbcTemplate jdbc, UUID caseId, String module, String schema,
            String payload) {
        UUID streamId = UUID.randomUUID();
        UUID versionId = UUID.randomUUID();
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version) "
                + "VALUES (?, ?, ?, ?, 2)", streamId, caseId, module, "module:" + module);
        insertVersion(jdbc, streamId, versionId, schema, payload);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                versionId, streamId);
        jdbc.update("INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale) "
                + "VALUES (?, ?, ?, ?, false)", caseId, module, streamId, versionId);
        return new Artifact(streamId, versionId, null);
    }

    private Artifact insertDraft(JdbcTemplate jdbc, UUID caseId, UUID owner, String payload) {
        UUID draftId = UUID.randomUUID();
        UUID streamId = UUID.randomUUID();
        UUID versionId = UUID.randomUUID();
        jdbc.update("INSERT INTO app.case_drafts(id, case_id, draft_type, render_doc_type, updated_by) "
                + "VALUES (?, ?, 'judgment', 'judgment-' || ?::text, ?)", draftId, caseId, draftId, owner);
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version) "
                + "VALUES (?, ?, 'draft', ?, 2)", streamId, caseId, "draft:" + draftId);
        insertVersion(jdbc, streamId, versionId, "draft.v2", payload);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                versionId, streamId);
        jdbc.update("INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale) "
                + "VALUES (?, ?, ?, ?, false)", draftId, caseId, streamId, versionId);
        return new Artifact(streamId, versionId, draftId);
    }

    private void insertVersion(JdbcTemplate jdbc, UUID streamId, UUID versionId, String schema,
            String payload) {
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, "
                + "schema_version, outcome_status, payload, dependency_snapshot, output_hash) "
                + "VALUES (?, ?, 1, ?, 'calculated', ?::jsonb, '{\"as_of_date\":\"2026-01-01\"}'::jsonb, 'temporal')",
                versionId, streamId, schema, payload);
    }

    private void dependency(JdbcTemplate jdbc, UUID downstream, UUID upstream) {
        jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, "
                + "depends_on_artifact_version_id) VALUES (?, ?)", downstream, upstream);
    }

    private UUID insertCase(JdbcTemplate jdbc, UUID owner) {
        UUID caseId = UUID.randomUUID();
        jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json) "
                + "VALUES (?, ?, 'temporal migration case', 'CN', '2026-01-01', '{}'::jsonb)", caseId, owner);
        return caseId;
    }

    private void insertAccount(JdbcTemplate jdbc, UUID owner) {
        jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) "
                + "VALUES (?, ?, ?, 'Temporal migration', 'hash')", owner,
                "temporal_" + owner, "temporal_" + owner);
    }

    private void assertHead(JdbcTemplate jdbc, String table, UUID id, boolean stale, String reason) {
        String column = table.equals("module_head") ? "artifact_stream_id" : "draft_id";
        assertEquals(stale, jdbc.queryForObject("SELECT stale FROM app." + table + " WHERE " + column + " = ?",
                Boolean.class, id));
        assertEquals(reason, jdbc.queryForObject("SELECT stale_reason FROM app." + table + " WHERE " + column + " = ?",
                String.class, id));
    }

    private UUID latest(JdbcTemplate jdbc, UUID streamId) {
        return jdbc.queryForObject("SELECT latest_version_id FROM app.artifact_stream WHERE artifact_stream_id = ?",
                UUID.class, streamId);
    }

    private UUID confirmed(JdbcTemplate jdbc, UUID streamId) {
        return jdbc.queryForObject("SELECT confirmed_version_id FROM app.module_head WHERE artifact_stream_id = ?",
                UUID.class, streamId);
    }

    private UUID approved(JdbcTemplate jdbc, UUID draftId) {
        return jdbc.queryForObject("SELECT approved_version_id FROM app.draft_head WHERE draft_id = ?",
                UUID.class, draftId);
    }

    private void assertPayload(JdbcTemplate jdbc, UUID versionId, String expected) {
        assertEquals(Boolean.TRUE, jdbc.queryForObject(
                "SELECT payload = ?::jsonb FROM app.artifact_version WHERE artifact_version_id = ?",
                Boolean.class, expected, versionId));
    }

    private boolean dockerAvailable() {
        try {
            return DockerClientFactory.instance().isDockerAvailable();
        } catch (RuntimeException unavailable) {
            return false;
        }
    }

    private record Artifact(UUID streamId, UUID versionId, UUID headId) {}
}
