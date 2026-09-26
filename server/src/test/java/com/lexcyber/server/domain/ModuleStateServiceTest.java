package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
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

class ModuleStateServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private ModuleStateService modules;
    private FactService facts;
    private CaseService cases;
    private UUID alice;
    private UUID bob;
    private CaseView aliceCase;
    private CaseView bobCase;

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
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        cases = new CaseService(jdbc, mapper, new IdempotencyService(jdbc));
        facts = new FactService(jdbc, cases, new FactsBaselineService(jdbc, new StalePropagationService(jdbc)));
        modules = new ModuleStateService(jdbc, mapper, cases,
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc)),
                new ModuleConfirmationService(jdbc), true);
        alice = insertAccount(jdbc, "alice_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        bob = insertAccount(jdbc, "bob_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        aliceCase = cases.create(alice, new CaseCreate("alice-modules", "CN", null, Map.of()));
        bobCase = cases.create(bob, new CaseCreate("bob-modules", "CN", null, Map.of()));
    }

    @Test
    void emptyGetIsDraftZeroAndOwnerScoped() {
        ModuleStateView empty = modules.get(alice, aliceCase.id(), "compliance");
        assertEquals("draft", empty.status());
        assertEquals(0, empty.version());
        assertEquals("unknown", empty.applicability());
        assertEquals(Map.of(), empty.content());
        assertFalse(empty.factsStale());

        ApiException hidden = assertThrows(ApiException.class,
                () -> modules.get(bob, aliceCase.id(), "compliance"));
        assertEquals(HttpStatus.NOT_FOUND, hidden.status());
        assertEquals("CASE_NOT_FOUND", hidden.code());

        ApiException missing = assertThrows(ApiException.class,
                () -> modules.get(alice, "case-missing", "conviction"));
        assertEquals("CASE_NOT_FOUND", missing.code());
    }

    @Test
    void putIncrementsVersionAndRejectsStaleOrConfirmedWrite() {
        ModuleStateView written = modules.replace(alice, aliceCase.id(), "conviction",
                new ModuleStateUpdate("limited_context", Map.of("note", "opaque"), "sv-1", 0));
        assertEquals(1, written.version());
        assertEquals("draft", written.status());
        assertEquals("limited_context", written.applicability());
        assertEquals("opaque", written.content().get("note"));
        assertEquals("sv-1", written.sourceVersion());

        ApiException stale = assertThrows(ApiException.class,
                () -> modules.replace(alice, aliceCase.id(), "conviction",
                        new ModuleStateUpdate(null, Map.of("note", "old"), null, 0)));
        assertEquals("MODULE_VERSION_CONFLICT", stale.code());

        ModuleStateView confirmed = modules.confirm(alice, aliceCase.id(), "conviction");
        assertEquals("confirmed", confirmed.status());
        ApiException locked = assertThrows(ApiException.class,
                () -> modules.replace(alice, aliceCase.id(), "conviction",
                        new ModuleStateUpdate(null, Map.of("note", "after"), null, 1)));
        assertEquals("MODULE_CONFIRMED", locked.code());
        ApiException again = assertThrows(ApiException.class,
                () -> modules.confirm(alice, aliceCase.id(), "conviction"));
        assertEquals("MODULE_CONFIRMED", again.code());
    }

    @Test
    void factsStaleFollowsFactEnvelopeClock() {
        ModuleStateView beforeFacts = modules.get(alice, aliceCase.id(), "compliance");
        assertFalse(beforeFacts.factsStale());

        facts.replace(alice, aliceCase.id(),
                new FactUpdate(List.of(new FactItem(null, "amount", "100", "paragraph:1", "doc-1"))));
        ModuleStateView staleEmpty = modules.get(alice, aliceCase.id(), "compliance");
        assertTrue(staleEmpty.factsStale());

        ModuleStateView snapshotted = modules.replace(alice, aliceCase.id(), "compliance",
                new ModuleStateUpdate("applicable", Map.of(), null, 0));
        assertFalse(snapshotted.factsStale());

        facts.replace(alice, aliceCase.id(),
                new FactUpdate(List.of(new FactItem(null, "amount", "200", "paragraph:1", "doc-1"))));
        assertTrue(modules.get(alice, aliceCase.id(), "compliance").factsStale());
    }

    @Test
    void writesRetiredUnlessDemoImportEnabled() {
        DataSource dataSource = dataSource();
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        ModuleStateService gated = new ModuleStateService(jdbc, mapper, cases,
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc)),
                new ModuleConfirmationService(jdbc), false);

        ApiException put = assertThrows(ApiException.class,
                () -> gated.replace(alice, aliceCase.id(), "conviction",
                        new ModuleStateUpdate(null, Map.of("note", "x"), null, 0)));
        assertEquals(HttpStatus.GONE, put.status());
        assertEquals("MODULE_WRITE_RETIRED", put.code());

        ApiException confirm = assertThrows(ApiException.class,
                () -> gated.confirm(alice, aliceCase.id(), "conviction"));
        assertEquals(HttpStatus.GONE, confirm.status());
        assertEquals("MODULE_WRITE_RETIRED", confirm.code());

        ModuleStateView view = gated.get(alice, aliceCase.id(), "conviction");
        assertEquals("draft", view.status());
    }

    private UUID insertAccount(JdbcTemplate jdbc, String username) {
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
