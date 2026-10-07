package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.EngineCapabilitiesClient;
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
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;

class TaskRetryLifecycleTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();
    private static PostgreSQLContainer<?> postgres;
    private JdbcTemplate jdbc;
    private TaskService tasks;
    private EngineCapabilitiesClient capabilities;
    private UUID owner;
    private String caseId;
    private UUID factsVersion;

    @BeforeAll
    static void openDatabase() {
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) return;
        postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber").withUsername("lex_app").withPassword("lex_app");
        postgres.start();
    }

    @AfterAll
    static void closeDatabase() {
        if (postgres != null) postgres.stop();
    }

    @BeforeEach
    void setup() {
        DataSource ds = dataSource();
        Flyway.configure().dataSource(ds).schemas("app")
                .locations("classpath:db/migration/app").load().migrate();
        jdbc = new JdbcTemplate(ds);
        capabilities = mock(EngineCapabilitiesClient.class);
        when(capabilities.moduleAvailable("compliance")).thenReturn(true);
        tasks = new TaskService(jdbc, MAPPER, false, capabilities);
        owner = UUID.randomUUID();
        jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) VALUES (?, ?, ?, ?, ?)",
                owner, "retry_" + owner, owner.toString(), "Retry", "hash");
        caseId = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, metadata_json) VALUES (?::uuid, ?, 'retry', 'CN', '{}'::jsonb)",
                caseId, owner);
        factsVersion = UUID.randomUUID();
        jdbc.update("INSERT INTO app.facts_head(case_id) VALUES (?::uuid)", caseId);
        jdbc.update("INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash, payload, created_by, confirmed_by, confirmed_at) VALUES (?, ?::uuid, 1, 'f', '{}'::jsonb, ?, ?, now())",
                factsVersion, caseId, owner, owner);
        jdbc.update("UPDATE app.facts_head SET confirmed_facts_version_id=? WHERE case_id=?::uuid", factsVersion, caseId);
    }

    @Test
    void failedV2RetryPreservesFrozenMetadataAndBinding() {
        UUID taskId = createV2Task();
        jdbc.update("UPDATE app.tasks SET status='failed' WHERE id=?", taskId);
        tasks.retry(taskId);
        assertEquals(2, jdbc.queryForObject("SELECT COUNT(*) FROM app.task_dispatch_outbox WHERE task_id=?", Integer.class, taskId));
        Map<String, Object> original = jdbc.queryForMap("SELECT payload_json->>'input_snapshot_ref' AS ref, payload_json->>'artifact_stream_id' AS stream FROM app.task_dispatch_outbox WHERE task_id=? ORDER BY id LIMIT 1", taskId);
        Map<String, Object> retry = jdbc.queryForMap("SELECT payload_json->>'input_snapshot_ref' AS ref, payload_json->>'artifact_stream_id' AS stream FROM app.task_dispatch_outbox WHERE task_id=? ORDER BY id DESC LIMIT 1", taskId);
        assertEquals(original.get("ref"), retry.get("ref"));
        assertEquals(original.get("stream"), retry.get("stream"));
        assertEquals("queued", jdbc.queryForObject("SELECT status FROM app.tasks WHERE id=?", String.class, taskId));
    }

    @Test
    void unavailableCapabilityDoesNotWriteRetryOutbox() {
        UUID taskId = createV2Task();
        jdbc.update("UPDATE app.tasks SET status='failed' WHERE id=?", taskId);
        when(capabilities.moduleAvailable("compliance")).thenReturn(false);
        assertThrows(ApiException.class, () -> tasks.retry(taskId));
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM app.task_dispatch_outbox WHERE task_id=?", Integer.class, taskId));
        assertEquals("failed", jdbc.queryForObject("SELECT status FROM app.tasks WHERE id=?", String.class, taskId));
    }

    @Test
    void changedFactsRejectsRetryWithoutWrites() {
        UUID taskId = createV2Task();
        jdbc.update("UPDATE app.tasks SET status='failed' WHERE id=?", taskId);
        UUID newer = UUID.randomUUID();
        jdbc.update("INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash, payload, created_by, confirmed_by, confirmed_at) VALUES (?, ?::uuid, 2, 'g', '{}'::jsonb, ?, ?, now())",
                newer, caseId, owner, owner);
        jdbc.update("UPDATE app.facts_head SET confirmed_facts_version_id=? WHERE case_id=?::uuid", newer, caseId);
        ApiException error = assertThrows(ApiException.class, () -> tasks.retry(taskId));
        assertEquals("DEPENDENCY_STALE", error.code());
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM app.task_dispatch_outbox WHERE task_id=?", Integer.class, taskId));
    }

    @Test
    void invalidStateAndLegacyGateRemainConflicts() {
        UUID taskId = createV2Task();
        assertThrows(org.springframework.web.server.ResponseStatusException.class, () -> tasks.retry(taskId));
        TaskService legacy = new TaskService(jdbc, MAPPER, false);
        ApiException error = assertThrows(ApiException.class, () -> legacy.create(new TaskCreate("q", caseId, null,
                Map.of("taskType", TaskPolicies.COMPLIANCE_ANALYZE))));
        assertEquals(HttpStatus.NOT_IMPLEMENTED, error.status());
        TaskView publicTask = legacy.create(new TaskCreate("q", null, null,
                Map.of("taskType", TaskPolicies.MODEL_PROBE, "_dispatchOrigin", "v2")));
        String metadata = jdbc.queryForObject("SELECT metadata_json::text FROM app.tasks WHERE id=?", String.class, publicTask.id());
        assertFalse(metadata.contains("_dispatchOrigin"));
    }

    private UUID createV2Task() {
        TaskView task = tasks.createModuleTask(new TaskCreate("module:compliance", caseId, null,
                Map.of("taskType", TaskPolicies.COMPLIANCE_ANALYZE, "module", "compliance",
                        "factsVersionId", factsVersion.toString(), "factsSnapshot", Map.of("facts", "frozen"))));
        return task.id();
    }

    private DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) {
            ds.setUrl(EXTERNAL_JDBC);
            ds.setUsername(envOr("TEST_JDBC_USER", "lex_app"));
            ds.setPassword(envOr("TEST_JDBC_PASSWORD", "lex_app"));
        } else {
            ds.setUrl(postgres.getJdbcUrl()); ds.setUsername(postgres.getUsername()); ds.setPassword(postgres.getPassword());
        }
        return ds;
    }

    private static String envOr(String name, String fallback) {
        String value = System.getenv(name); return value == null || value.isBlank() ? fallback : value;
    }
}
