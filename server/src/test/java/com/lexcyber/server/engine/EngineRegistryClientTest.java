package com.lexcyber.server.engine;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.lexcyber.server.api.ApiException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import javax.sql.DataSource;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RestClient;
import org.testcontainers.containers.PostgreSQLContainer;

/** Real PostgreSQL and HTTP regression coverage for the registry validity gate. */
class EngineRegistryClientTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;
    private JdbcTemplate jdbc;
    private TransactionTemplate tx;
    private HttpServer server;
    private JdbcTemplate handlerJdbc;
    private AtomicReference<String> response;
    private AtomicReference<Map<String, Object>> request;
    private AtomicReference<Throwable> handlerError;
    private AtomicReference<Integer> handlerPid;
    private AtomicReference<Long> handlerChallenge;
    private EngineRegistryClient client;

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
    void setup() throws IOException {
        DataSource dataSource = dataSource();
        Flyway.configure().dataSource(dataSource).schemas("app")
                .locations("classpath:db/migration/app").load().migrate();
        jdbc = new JdbcTemplate(dataSource);
        handlerJdbc = new JdbcTemplate(dataSource);
        tx = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        response = new AtomicReference<>("{\"valid\":true,\"invalidDependencies\":[]}");
        request = new AtomicReference<>();
        handlerError = new AtomicReference<>();
        handlerPid = new AtomicReference<>();
        handlerChallenge = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/registry/verify-dependencies", this::respond);
        server.start();
        client = new EngineRegistryClient(RestClient.builder(),
                "http://127.0.0.1:" + server.getAddress().getPort(), "registry-test-token");
    }

    @AfterEach
    void closeServer() {
        if (server != null) server.stop(0);
    }

    @Test
    void verifiesTwoLevelClosureDeduplicatesAndHoldsBothAdvisorySharesDuringHttp() {
        UUID root = fixtureWithTwoLevelClosure();
        tx.executeWithoutResult(status -> client.requireValid(jdbc, root));
        assertTrue(handlerError.get() == null, () -> String.valueOf(handlerError.get()));

        Map<String, Object> body = request.get();
        assertEquals("registry-test-token", body.get("_token"));
        @SuppressWarnings("unchecked")
        Map<String, Object> coordination = (Map<String, Object>) body.get("coordination");
        int pid = ((Number) coordination.get("backendPid")).intValue();
        long challenge = Long.parseLong(String.valueOf(coordination.get("challenge")));
        assertNotEquals(EngineRegistryClient.REGISTRY_BARRIER, challenge);
        assertEquals(0, jdbc.queryForObject("""
                SELECT COUNT(*) FROM pg_locks
                WHERE pid = ? AND locktype = 'advisory' AND granted
                  AND objsubid = 1
                  AND classid = ((?::bigint >> 32) & 4294967295)::oid
                  AND objid = (?::bigint & 4294967295)::oid
                """, Integer.class, pid, EngineRegistryClient.REGISTRY_BARRIER,
                EngineRegistryClient.REGISTRY_BARRIER));
        assertEquals(0, jdbc.queryForObject("""
                SELECT COUNT(*) FROM pg_locks
                WHERE pid = ? AND locktype = 'advisory' AND granted
                  AND objsubid = 1
                  AND classid = ((?::bigint >> 32) & 4294967295)::oid
                  AND objid = (?::bigint & 4294967295)::oid
                """, Integer.class, pid, challenge, challenge));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> dependencies = (List<Map<String, Object>>) body.get("dependencies");
        assertEquals(2, dependencies.size());
        assertTrue(dependencies.stream().anyMatch(dep -> "rule".equals(dep.get("kind"))
                && "registry-rule".equals(dep.get("key")) && "1".equals(dep.get("version"))));
        assertTrue(dependencies.stream().anyMatch(dep -> "template".equals(dep.get("kind"))
                && "registry-template".equals(dep.get("key")) && "2".equals(dep.get("version"))));
    }

    @Test
    void invalidRegistryDependencyMapsToConflictAndDoesNotMutateApplicationRows() {
        UUID root = fixtureWithTwoLevelClosure();
        response.set("{\"valid\":false,\"invalidDependencies\":[{\"kind\":\"rule\",\"key\":\"registry-rule\",\"version\":\"1\",\"reason\":\"revoked\"}]}");
        ApiException error = assertThrows(ApiException.class,
                () -> tx.executeWithoutResult(status -> client.requireValid(jdbc, root)));
        assertEquals(HttpStatus.CONFLICT, error.status());
        assertEquals("DEPENDENCY_STALE", error.code());
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.module_head WHERE stale_reason='dependency_changed'", Integer.class));
    }

    @Test
    void unavailableAndMalformedResponsesFailClosedAndEmptyVersionIsConflict() {
        UUID root = fixtureWithTwoLevelClosure();
        response.set("{\"valid\":true}");
        ApiException malformed = assertThrows(ApiException.class,
                () -> tx.executeWithoutResult(status -> client.requireValid(jdbc, root)));
        assertEquals("REGISTRY_VERIFICATION_UNAVAILABLE", malformed.code());

        response.set("{\"valid\":false,\"invalidDependencies\":[]}");
        ApiException inconsistent = assertThrows(ApiException.class,
                () -> tx.executeWithoutResult(status -> client.requireValid(jdbc, root)));
        assertEquals("REGISTRY_VERIFICATION_UNAVAILABLE", inconsistent.code());

        response.set("service-unavailable");
        server.removeContext("/internal/v1/registry/verify-dependencies");
        server.createContext("/internal/v1/registry/verify-dependencies",
                exchange -> respond(exchange, 503, "{}"));
        ApiException unavailable = assertThrows(ApiException.class,
                () -> tx.executeWithoutResult(status -> client.requireValid(jdbc, root)));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, unavailable.status());

        UUID empty = UUID.randomUUID();
        emptyDependencyArtifact(empty);
        jdbc.update("INSERT INTO app.artifact_external_dependency(artifact_version_id, dependency_kind, dependency_key, dependency_version) VALUES (?, 'rule', 'registry-rule', '')", empty);
        ApiException blank = assertThrows(ApiException.class,
                () -> tx.executeWithoutResult(status -> client.requireValid(jdbc, empty)));
        assertEquals("DEPENDENCY_STALE", blank.code());
    }

    @Test
    void configuredClientRequiresAnActiveTransaction() {
        UUID root = fixtureWithTwoLevelClosure();
        ApiException error = assertThrows(ApiException.class, () -> client.requireValid(jdbc, root));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, error.status());
        assertEquals("REGISTRY_VERIFICATION_UNAVAILABLE", error.code());
    }

    private UUID emptyDependencyArtifact(UUID id) {
        UUID stream = UUID.randomUUID();
        UUID caseId = UUID.randomUUID();
        UUID account = UUID.randomUUID();
        jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) VALUES (?, ?, ?, 'registry', 'hash')", account, "registry_" + account, "registry_" + account);
        jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction) VALUES (?, ?, 'registry', 'CI')", caseId, account);
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key) VALUES (?, ?, 'compliance', 'module:compliance')", stream, caseId);
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, schema_version, outcome_status, payload, dependency_snapshot, output_hash) VALUES (?, ?, 1, 'case.compliance.v2', 'calculated', '{}'::jsonb, '{}'::jsonb, 'empty')", id, stream);
        return id;
    }

    private UUID fixtureWithTwoLevelClosure() {
        UUID account = UUID.randomUUID();
        UUID caseId = UUID.randomUUID();
        UUID root = UUID.randomUUID();
        UUID child = UUID.randomUUID();
        UUID grandchild = UUID.randomUUID();
        UUID rootStream = UUID.randomUUID();
        UUID childStream = UUID.randomUUID();
        UUID grandchildStream = UUID.randomUUID();
        jdbc.update("INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash) VALUES (?, ?, ?, 'registry', 'hash')", account, "registry_" + account, "registry_" + account);
        jdbc.update("INSERT INTO app.cases(id, owner_account_id, title, jurisdiction) VALUES (?, ?, 'registry', 'CI')", caseId, account);
        insertArtifact(rootStream, root, caseId, "compliance", "registry-rule", "1");
        insertArtifact(childStream, child, caseId, "conviction", "registry-rule", "1");
        insertArtifact(grandchildStream, grandchild, caseId, "draft", "registry-template", "2");
        jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?), (?, ?)", child, root, grandchild, child);
        jdbc.update("INSERT INTO app.artifact_external_dependency(artifact_version_id, dependency_kind, dependency_key, dependency_version) VALUES (?, 'rule', 'registry-rule', '1'), (?, 'rule', 'registry-rule', '1'), (?, 'template', 'registry-template', '2')", root, child, grandchild);
        return grandchild;
    }

    private void insertArtifact(UUID stream, UUID version, UUID caseId, String kind, String key, String depVersion) {
        jdbc.update("INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key) VALUES (?, ?, ?, ?)", stream, caseId, kind, kind + ":registry");
        jdbc.update("INSERT INTO app.artifact_version(artifact_version_id, artifact_stream_id, version, schema_version, outcome_status, payload, dependency_snapshot, output_hash) VALUES (?, ?, 1, 'case.compliance.v2', 'calculated', '{}'::jsonb, '{}'::jsonb, ?)", version, stream, version.toString());
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id=? WHERE artifact_stream_id=?", version, stream);
    }

    private void respond(HttpExchange exchange) throws IOException {
        respond(exchange, 200, response.get());
    }

    private void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] raw = body.getBytes(StandardCharsets.UTF_8);
        if (status == 200) {
            try {
                String input = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                @SuppressWarnings("unchecked") Map<String, Object> decoded = new com.fasterxml.jackson.databind.ObjectMapper().readValue(input, Map.class);
                decoded.put("_token", exchange.getRequestHeaders().getFirst("X-Service-Token"));
                request.set(decoded);
                @SuppressWarnings("unchecked") Map<String, Object> coordination =
                        (Map<String, Object>) decoded.get("coordination");
                int pid = ((Number) coordination.get("backendPid")).intValue();
                long challenge = Long.parseLong(String.valueOf(coordination.get("challenge")));
                handlerPid.set(pid);
                handlerChallenge.set(challenge);
                int globalLocks = jdbcLocks(pid, EngineRegistryClient.REGISTRY_BARRIER);
                int challengeLocks = jdbcLocks(pid, challenge);
                if (globalLocks != 1 || challengeLocks != 1) {
                    throw new AssertionError("registry locks were not held through HTTP: global="
                            + globalLocks + ", challenge=" + challengeLocks);
                }
            } catch (Throwable ignored) {
                handlerError.set(ignored);
            }
        }
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, raw.length);
        exchange.getResponseBody().write(raw);
        exchange.close();
    }

    private int jdbcLocks(int pid, long key) {
        return handlerJdbc.queryForObject("""
                SELECT COUNT(*) FROM pg_locks
                WHERE pid = ? AND locktype = 'advisory' AND granted AND objsubid = 1
                  AND classid = ((?::bigint >> 32) & 4294967295)::oid
                  AND objid = (?::bigint & 4294967295)::oid
                """, Integer.class, pid, key, key);
    }

    private DataSource dataSource() {
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) return new DriverManagerDataSource(EXTERNAL_JDBC);
        return new DriverManagerDataSource(postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
    }
}
