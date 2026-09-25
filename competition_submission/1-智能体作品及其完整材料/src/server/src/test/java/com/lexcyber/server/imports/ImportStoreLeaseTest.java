package com.lexcyber.server.imports;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.util.Map;
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

class ImportStoreLeaseTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private ImportStore store;
    private JdbcTemplate jdbc;
    private UUID owner;
    private UUID batchId;
    private UUID itemId;
    private UUID stepId;

    @BeforeAll
    static void openDatabase() {
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) {
            return;
        }
        postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber")
                .withUsername("lex_app")
                .withPassword("lex_app");
        postgres.start();
    }

    @AfterAll
    static void closeDatabase() {
        if (postgres != null) {
            postgres.stop();
        }
    }

    @BeforeEach
    void setup() {
        DataSource dataSource = dataSource();
        Flyway.configure()
                .dataSource(dataSource)
                .schemas("app")
                .locations("classpath:db/migration/app")
                .load()
                .migrate();
        jdbc = new JdbcTemplate(dataSource);
        store = new ImportStore(jdbc, new ObjectMapper().findAndRegisterModules());
        owner = insertAccount("owner_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        batchId = UUID.randomUUID();
        itemId = UUID.randomUUID();
        stepId = UUID.randomUUID();
        seedApprovedBatch();
    }

    @Test
    void expiredWorkerTokensCannotClaimOrCompleteStepsAfterRecovery() {
        UUID stale = store.claimApplyLease(owner, batchId);
        store.lockApplyLease(owner, batchId, stale);
        store.claimStep(owner, batchId, stepId, stale);

        jdbc.update("UPDATE app.import_batches SET lease_expires_at = now() - interval '1 second' WHERE id = ?", batchId);
        store.recoverExpiredApply(owner, batchId);

        assertThrows(ApiException.class, () -> store.lockApplyLease(owner, batchId, stale));
        assertThrows(ApiException.class, () -> store.claimStep(owner, batchId, stepId, stale));
        assertThrows(ApiException.class, () -> store.completeStep(owner, batchId, stepId, stale, Map.of("x", "y")));

        UUID replacement = store.claimApplyLease(owner, batchId);
        store.lockApplyLease(owner, batchId, replacement);
        store.claimStep(owner, batchId, stepId, replacement);
        store.completeStep(owner, batchId, stepId, replacement, Map.of("caseId", "case-1"));

        assertThrows(ApiException.class, () -> store.completeStep(owner, batchId, stepId, stale, Map.of()));
        ImportStepView step = store.requireOwnedStep(owner, batchId, stepId);
        assertEquals("completed", step.status());
        assertEquals(2, step.attempt());
        assertEquals(Map.of("caseId", "case-1"), step.output());
    }

    private void seedApprovedBatch() {
        store.insertBatchReservation(owner, batchId,
                new RawPackageStorage.StoredRawPackage("raw/" + batchId, "bundle.zip", "application/zip", 128,
                        "0".repeat(64)),
                Map.of());
        jdbc.update("""
                UPDATE app.import_batches SET status = 'approved', approved_by = ?, approved_at = now()
                WHERE id = ?
                """, owner, batchId);
        store.insertItem(owner, new ImportItemCreate(itemId, batchId, 0, "item-1", "ext-case-1",
                "cases/case-1.json", "1".repeat(64), Map.of()));
        jdbc.update("UPDATE app.import_items SET status = 'approved' WHERE id = ?", itemId);
        store.insertStep(owner, new ImportStepCreate(stepId, batchId, itemId, "case.create", 0, Map.of()));
    }

    private UUID insertAccount(String username) {
        UUID id = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """, id, username, username, username, "hash");
        return id;
    }

    private DataSource dataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) {
            dataSource.setUrl(EXTERNAL_JDBC);
            dataSource.setUsername(envOr("TEST_JDBC_USER", "lex_app"));
            dataSource.setPassword(envOr("TEST_JDBC_PASSWORD", "lex_app"));
            return dataSource;
        }
        dataSource.setUrl(postgres.getJdbcUrl());
        dataSource.setUsername(postgres.getUsername());
        dataSource.setPassword(postgres.getPassword());
        return dataSource;
    }

    private static String envOr(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
