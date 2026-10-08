package com.lexcyber.server.engine;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RestClient;
import org.testcontainers.containers.PostgreSQLContainer;
import org.flywaydb.core.Flyway;

/** PostgreSQL regressions for durable registry invalidation application. */
class RegistryInvalidationReconcilerTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;
    private JdbcTemplate jdbc;
    private RegistryInvalidationReconciler reconciler;

    @BeforeAll
    static void openDatabase() {
        if (EXTERNAL_JDBC == null || EXTERNAL_JDBC.isBlank()) {
            postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                    .withDatabaseName("lexcyber").withUsername("lex_app").withPassword("lex_app");
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
        reconciler = new RegistryInvalidationReconciler(
                jdbc, RestClient.builder(), "http://engine", "test-token",
                new DataSourceTransactionManager(dataSource));
    }

    @Test
    void oldExactDependencyStalesModuleAndDownstreamDraftAndDuplicateReceiptIsIdempotent() {
        Fixture fixture = fixture();
        String rootPayloadBefore = jdbc.queryForObject(
                "SELECT payload::text FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, fixture.root());
        String draftPayloadBefore = jdbc.queryForObject(
                "SELECT payload::text FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, fixture.draftVersion());
        UUID eventId = UUID.randomUUID();
        RegistryInvalidationReconciler.InvalidationEvent event = event(eventId,
                OffsetDateTime.now(ZoneOffset.UTC).plusSeconds(1),
                new RegistryInvalidationReconciler.Dependency("rule", fixture.key(), "1"));

        assertTrue(apply(event));
        assertEquals(Boolean.TRUE, jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id=? AND module='compliance'",
                Boolean.class, fixture.caseId()));
        assertEquals("dependency_changed", jdbc.queryForObject(
                "SELECT stale_reason FROM app.module_head WHERE case_id=? AND module='compliance'",
                String.class, fixture.caseId()));
        assertEquals(Boolean.TRUE, jdbc.queryForObject(
                "SELECT stale FROM app.draft_head WHERE draft_id=?", Boolean.class, fixture.draftId()));
        assertEquals(fixture.root(), jdbc.queryForObject(
                "SELECT confirmed_version_id FROM app.module_head WHERE case_id=? AND module='compliance'",
                UUID.class, fixture.caseId()));
        assertEquals(fixture.draftVersion(), jdbc.queryForObject(
                "SELECT approved_version_id FROM app.draft_head WHERE draft_id=?", UUID.class, fixture.draftId()));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.registry_invalidation_applied WHERE event_id=?", Integer.class, eventId));
        assertEquals(rootPayloadBefore, jdbc.queryForObject(
                "SELECT payload::text FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, fixture.root()));
        assertEquals(draftPayloadBefore, jdbc.queryForObject(
                "SELECT payload::text FROM app.artifact_version WHERE artifact_version_id = ?",
                String.class, fixture.draftVersion()));

        assertTrue(apply(event));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.registry_invalidation_applied WHERE event_id=?", Integer.class, eventId));
    }

    @Test
    void unrelatedVersionStaysFreshButLegacyBlankStoredVersionInvalidatesConservatively() {
        Fixture fixture = fixture();
        assertTrue(apply(event(UUID.randomUUID(), OffsetDateTime.now(ZoneOffset.UTC),
                new RegistryInvalidationReconciler.Dependency("rule", fixture.key(), "2"))));
        assertFalse(jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id=? AND module='compliance'",
                Boolean.class, fixture.caseId()));

        jdbc.update("UPDATE app.artifact_external_dependency SET dependency_version='' WHERE artifact_version_id=?", fixture.root());
        assertTrue(apply(event(UUID.randomUUID(), OffsetDateTime.now(ZoneOffset.UTC),
                new RegistryInvalidationReconciler.Dependency("rule", fixture.key(), "1"))));
        assertTrue(jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id=? AND module='compliance'",
                Boolean.class, fixture.caseId()));
    }

    @Test
    void eventBeforeNewArtifactWithSameDependencyTupleDoesNotInvalidateFreshArtifact() {
        Fixture fixture = fixture();
        OffsetDateTime occurredAt = OffsetDateTime.now(ZoneOffset.UTC).minusSeconds(2);
        assertTrue(apply(event(UUID.randomUUID(), occurredAt,
                new RegistryInvalidationReconciler.Dependency("rule", fixture.key(), "1"))));
        assertFalse(jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id=? AND module='compliance'",
                Boolean.class, fixture.caseId()));
    }

    @Test
    void malformedEventsAreRejectedWithoutReceipt() {
        UUID invalidId = UUID.randomUUID();
        int before = jdbc.queryForObject("SELECT COUNT(*) FROM app.registry_invalidation_applied", Integer.class);
        RegistryInvalidationReconciler.Dependency blankVersion =
                new RegistryInvalidationReconciler.Dependency("rule", "rule-x", "");
        assertThrows(IllegalArgumentException.class,
                () -> apply(event(invalidId, OffsetDateTime.now(ZoneOffset.UTC), blankVersion)));
        assertEquals(before, jdbc.queryForObject("SELECT COUNT(*) FROM app.registry_invalidation_applied", Integer.class));

        RegistryInvalidationReconciler.InvalidationEvent malformed =
                new RegistryInvalidationReconciler.InvalidationEvent(
                        "not-a-uuid", OffsetDateTime.now(ZoneOffset.UTC),
                        List.of(new RegistryInvalidationReconciler.Dependency("rule", "rule-x", "1")));
        assertThrows(IllegalArgumentException.class, () -> apply(malformed));
        assertEquals(before, jdbc.queryForObject("SELECT COUNT(*) FROM app.registry_invalidation_applied", Integer.class));
    }

    private boolean apply(RegistryInvalidationReconciler.InvalidationEvent event) {
        TransactionTemplate tx = new TransactionTemplate(new DataSourceTransactionManager(jdbc.getDataSource()));
        return Boolean.TRUE.equals(tx.execute(status -> reconciler.apply(event)));
    }

    private static RegistryInvalidationReconciler.InvalidationEvent event(
            UUID id, OffsetDateTime occurredAt, RegistryInvalidationReconciler.Dependency dependency) {
        return new RegistryInvalidationReconciler.InvalidationEvent(id.toString(), occurredAt, List.of(dependency));
    }

    private Fixture fixture() {
        UUID account = UUID.randomUUID();
        UUID caseId = UUID.randomUUID();
        UUID rootStream = UUID.randomUUID();
        UUID root = UUID.randomUUID();
        UUID draft = UUID.randomUUID();
        UUID draftStream = UUID.randomUUID();
        UUID draftVersion = UUID.randomUUID();
        String key = "rule-" + UUID.randomUUID();
        jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) VALUES (?, ?, ?, 'test', 'hash')",
                account, "u_" + account, "u_" + account);
        jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction) VALUES (?, ?, 'registry', 'CN')",
                caseId, account);
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key) VALUES (?, ?, 'compliance', 'module:compliance')",
                rootStream, caseId);
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, schema_version, outcome_status, payload, dependency_snapshot, output_hash) "
                        + "VALUES (?, ?, 1, 'case.compliance.v2', 'calculated', '{}'::jsonb, '{}'::jsonb, 'root-hash')",
                root, rootStream);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id=? WHERE artifact_stream_id=?", root, rootStream);
        jdbc.update("INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale, stale_reason) VALUES (?, 'compliance', ?, ?, false, NULL)",
                caseId, rootStream, root);
        jdbc.update("INSERT INTO app.case_drafts(id, case_id, draft_type, updated_by) VALUES (?, ?, 'indictment', ?)",
                draft, caseId, account);
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key) VALUES (?, ?, 'draft', ?)",
                draftStream, caseId, "draft:" + draft);
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, schema_version, outcome_status, payload, dependency_snapshot, output_hash) "
                        + "VALUES (?, ?, 1, 'draft.v2', 'calculated', '{}'::jsonb, '{}'::jsonb, 'draft-hash')",
                draftVersion, draftStream);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id=? WHERE artifact_stream_id=?", draftVersion, draftStream);
        jdbc.update("INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale, stale_reason) VALUES (?, ?, ?, ?, false, NULL)",
                draft, caseId, draftStream, draftVersion);
        jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?)",
                draftVersion, root);
        jdbc.update("INSERT INTO app.artifact_external_dependency(artifact_version_id, dependency_kind, dependency_key, dependency_version) VALUES (?, 'rule', ?, '1')",
                root, key);
        return new Fixture(account, caseId, root, draft, draftVersion, key);
    }

    private DataSource dataSource() {
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) {
            DriverManagerDataSource dataSource = new DriverManagerDataSource();
            dataSource.setUrl(EXTERNAL_JDBC);
            dataSource.setUsername(envOr("TEST_JDBC_USER", "lex_app"));
            dataSource.setPassword(envOr("TEST_JDBC_PASSWORD", "lex_app"));
            return dataSource;
        }
        DriverManagerDataSource dataSource = new DriverManagerDataSource(postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
        return dataSource;
    }

    private static String envOr(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private record Fixture(UUID account, UUID caseId, UUID root, UUID draftId,
                           UUID draftVersion, String key) {}
}
