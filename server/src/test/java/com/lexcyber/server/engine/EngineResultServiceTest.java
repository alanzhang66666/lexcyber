package com.lexcyber.server.engine;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.domain.ArtifactPublicationService;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.DraftApprovalService;
import com.lexcyber.server.domain.IdempotencyService;
import com.lexcyber.server.domain.ModuleConfirmationService;
import com.lexcyber.server.domain.StalePropagationService;
import com.lexcyber.server.review.ReviewService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.testcontainers.containers.PostgreSQLContainer;

/** Regression coverage for callback fencing and review-opening idempotency. */
class EngineResultServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private JdbcTemplate jdbc;
    private ArtifactPublicationService artifacts;
    private EngineResultService service;
    private UUID account;
    private UUID caseId;
    private UUID taskId;
    private UUID requestId;
    private UUID currentExecution;
    private UUID documentId;

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
        if (postgres != null) {
            postgres.stop();
        }
    }

    @BeforeEach
    void setup() {
        DataSource dataSource = dataSource();
        Flyway.configure().dataSource(dataSource).schemas("app")
                .locations("classpath:db/migration/app").load().migrate();
        jdbc = new JdbcTemplate(dataSource);
        artifacts = new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc));
        service = new EngineResultService(jdbc, artifacts, new ObjectMapper());

        account = UUID.randomUUID();
        caseId = UUID.randomUUID();
        taskId = UUID.randomUUID();
        requestId = UUID.randomUUID();
        currentExecution = UUID.randomUUID();
        documentId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """, account, "u_" + account, "u_" + account, "Test", "hash");
        jdbc.update("""
                INSERT INTO app.cases(id, owner_account_id, title, jurisdiction)
                VALUES (?, ?, 'callback-test', 'CN')
                """, caseId, account);
        jdbc.update("""
                INSERT INTO app.tasks(id, request_id, execution_id, case_id, query_text, status, current_stage)
                VALUES (?, ?, ?, ?, 'parse', 'queued', 'parse')
                """, taskId, requestId, currentExecution, caseId);
        jdbc.update("""
                INSERT INTO app.documents(id, case_id, filename, content_type, size, role, storage_key, sha256, parse_status, parse_task_id)
                VALUES (?, ?, 'input.txt', 'text/plain', 1, 'input', 'k', 'h', 'queued', ?)
                """, documentId, caseId, taskId);
    }

    @Test
    void lateOldExecutionIsAuditedButCannotPublishOrChangeTaskOrDocument() {
        UUID oldExecution = UUID.randomUUID();
        UUID currentResultId = UUID.randomUUID();
        UUID resultId = UUID.randomUUID();
        addDispatch(currentExecution, currentResultId, 1);
        service.accept(envelope(currentExecution, currentResultId, "{\"current\":true}", true));
        addDispatch(oldExecution, resultId, 1);
        String content = "{\"old\":true}";
        UUID oldLatest = jdbc.queryForObject("""
                SELECT latest_version_id FROM app.artifact_stream
                WHERE case_id=? AND kind='parse' AND scope_key=?
                """, UUID.class, caseId, "document:" + documentId);

        Map<String, Object> result = service.accept(envelope(oldExecution, resultId, content, false));

        assertEquals(Boolean.TRUE, result.get("stale"));
        assertEquals(currentExecution, jdbc.queryForObject(
                "SELECT execution_id FROM app.tasks WHERE id=?", UUID.class, taskId));
        assertEquals("waiting_review", jdbc.queryForObject(
                "SELECT status FROM app.tasks WHERE id=?", String.class, taskId));
        assertEquals("waiting_review", jdbc.queryForObject(
                "SELECT parse_status FROM app.documents WHERE parse_task_id=?", String.class, taskId));
        assertEquals(oldLatest, jdbc.queryForObject(
                "SELECT latest_version_id FROM app.artifact_stream WHERE case_id=? AND kind='parse' AND scope_key=?",
                UUID.class, caseId, "document:" + documentId));
        assertEquals(1L, jdbc.queryForObject(
                "SELECT count(*) FROM app.review_records WHERE artifact_version_id=?", Long.class, oldLatest));
    }

    @Test
    void publicationPreservesBothLegalVersionsAndDeduplicatesPointReferences() {
        UUID resultId = UUID.randomUUID();
        addDispatch(currentExecution, resultId, 1);
        String content = """
                {"text":"versioned sources","dependency_snapshot":{
                  "rules":[
                    {"ruleId":"same-rule","ruleVersion":"1","family":"compliance"},
                    {"ruleId":"same-rule","ruleVersion":"1"}
                  ],
                  "sources":["source-old","source-new","legacy-source"],
                  "source_versions":[
                    {"sourceId":"source-old","sourceVersion":"2024","point":"conduct"},
                    {"sourceId":"source-old","sourceVersion":"2024","point":"judgment"},
                    {"sourceId":"source-new","sourceVersion":"2026","point":"judgment"}
                  ]}}
                """;
        ResultEnvelope callback = envelope(currentExecution, resultId, content, true);
        service.accept(callback);
        service.accept(callback);

        UUID version = jdbc.queryForObject(
                "SELECT artifact_version_id FROM app.artifact_version WHERE execution_id = ?",
                UUID.class, currentExecution);
        assertEquals(4, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.artifact_external_dependency WHERE artifact_version_id = ?",
                Integer.class, version));
        assertEquals(1, jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.artifact_external_dependency
                WHERE artifact_version_id = ? AND dependency_kind = 'rule' AND dependency_key = 'same-rule'
                """, Integer.class, version));
        assertEquals("2024", jdbc.queryForObject("""
                SELECT dependency_version FROM app.artifact_external_dependency
                WHERE artifact_version_id = ? AND dependency_kind = 'legal_source' AND dependency_key = 'source-old'
                """, String.class, version));
        assertEquals("2026", jdbc.queryForObject("""
                SELECT dependency_version FROM app.artifact_external_dependency
                WHERE artifact_version_id = ? AND dependency_kind = 'legal_source' AND dependency_key = 'source-new'
                """, String.class, version));
        assertEquals("", jdbc.queryForObject("""
                SELECT dependency_version FROM app.artifact_external_dependency
                WHERE artifact_version_id = ? AND dependency_kind = 'legal_source' AND dependency_key = 'legacy-source'
                """, String.class, version));
    }

    @Test
    void malformedExplicitLegalVersionCannotPublishAnArtifact() {
        UUID resultId = UUID.randomUUID();
        addDispatch(currentExecution, resultId, 1);
        String content = "{\"dependency_snapshot\":{\"source_versions\":[{\"sourceId\":\"source\",\"sourceVersion\":\"\"}]}}";

        ResponseStatusException error = assertThrows(ResponseStatusException.class,
                () -> service.accept(envelope(currentExecution, resultId, content, true)));

        assertEquals(409, error.getStatusCode().value());
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.artifact_version WHERE execution_id = ?",
                Integer.class, currentExecution));
    }

    @Test
    void duplicateCallbackDoesNotCreateSecondReviewOrReopenDecision() {
        UUID resultId = UUID.randomUUID();
        addDispatch(currentExecution, resultId, 1);
        String content = "{\"ok\":true}";
        service.accept(envelope(currentExecution, resultId, content, true));
        UUID artifactVersion = jdbc.queryForObject("""
                SELECT latest_version_id FROM app.artifact_stream
                WHERE case_id=? AND kind='parse' AND scope_key=?
                """, UUID.class, caseId, "document:" + documentId);
        UUID reviewId = jdbc.queryForObject(
                "SELECT review_id FROM app.review_records WHERE artifact_version_id=?", UUID.class, artifactVersion);
        jdbc.update("UPDATE app.review_records SET status='approved', decided_at=now() WHERE review_id=?", reviewId);
        service.accept(envelope(currentExecution, resultId, content, true));

        assertEquals(1L, jdbc.queryForObject(
                "SELECT count(*) FROM app.review_records WHERE artifact_version_id=?", Long.class, artifactVersion));
        assertEquals("approved", jdbc.queryForObject(
                "SELECT status FROM app.review_records WHERE review_id=?", String.class, reviewId));
    }

    @Test
    void failedCallbackWithContentDoesNotPublishArtifact() {
        UUID resultId = UUID.randomUUID();
        addDispatch(currentExecution, resultId, 1);
        service.accept(envelopeStatus(currentExecution, resultId, "{\"failed\":true}", "failed", Map.of()));

        assertEquals("failed", jdbc.queryForObject(
                "SELECT status FROM app.tasks WHERE id=?", String.class, taskId));
        assertEquals(0L, jdbc.queryForObject(
                "SELECT count(*) FROM app.artifact_stream WHERE case_id=?", Long.class, caseId));
    }

    @Test
    void failedCallbackCannotRollbackAlreadyPublishedCompletion() {
        UUID completedResult = UUID.randomUUID();
        addDispatch(currentExecution, completedResult, 1);
        service.accept(envelope(currentExecution, completedResult, "{\"ok\":true}", true));
        UUID latest = jdbc.queryForObject("""
                SELECT latest_version_id FROM app.artifact_stream
                WHERE case_id=? AND kind='parse' AND scope_key=?
                """, UUID.class, caseId, "document:" + documentId);

        // A retry for the same execution/completion is bound to the original
        // outbox identity; it must not introduce a second dispatch identity.
        service.accept(envelopeStatus(currentExecution, completedResult, null, "failed", Map.of()));

        assertEquals("waiting_review", jdbc.queryForObject(
                "SELECT status FROM app.tasks WHERE id=?", String.class, taskId));
        assertEquals(latest, jdbc.queryForObject("""
                SELECT latest_version_id FROM app.artifact_stream
                WHERE case_id=? AND kind='parse' AND scope_key=?
                """, UUID.class, caseId, "document:" + documentId));
    }

    @Test
    void hashAndOutboxMismatchesAreRejected() {
        UUID hashResult = UUID.randomUUID();
        addDispatch(currentExecution, hashResult, 1);
        ResultEnvelope base = envelope(currentExecution, hashResult, "{\"x\":1}", false);
        final ResultEnvelope wrongHash = new ResultEnvelope(base.executionId(), base.taskId(), base.requestId(),
                base.resultId(), base.resultVersion(), base.resultType(), base.status(), base.currentStage(),
                base.contentJson(), "00".repeat(32), base.errorCode(), base.errorMessage(), base.retryable(),
                base.resultRef(), base.fencingToken(), base.completionIdentity(), base.outputEnvelope());
        assertThrows(ResponseStatusException.class, () -> service.accept(wrongHash));

        UUID unboundResult = UUID.randomUUID();
        assertThrows(ResponseStatusException.class,
                () -> service.accept(envelope(currentExecution, unboundResult, "{\"x\":2}", false)));
    }

    @Test
    void concurrentFirstAcceptPublishesOnceAndReplayAfterApprovalDoesNotReopenOrRegress() throws Exception {
        UUID resultId = UUID.randomUUID();
        addDispatch(currentExecution, resultId, 1);
        String content = "{\"ok\":true,\"race\":true}";
        ResultEnvelope callback = envelope(currentExecution, resultId, content, true);
        TransactionTemplate boundedTx = new TransactionTemplate(
                new DataSourceTransactionManager(jdbc.getDataSource()));
        boundedTx.setTimeout(10);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CyclicBarrier firstStart = new CyclicBarrier(2);
            Future<Map<String, Object>> first = submitAccept(executor, firstStart, boundedTx, callback);
            Future<Map<String, Object>> second = submitAccept(executor, firstStart, boundedTx, callback);
            assertEquals(Boolean.FALSE, first.get(5, TimeUnit.SECONDS).get("stale"));
            assertEquals(Boolean.FALSE, second.get(5, TimeUnit.SECONDS).get("stale"));

            UUID artifactVersion = jdbc.queryForObject("""
                    SELECT v.artifact_version_id
                    FROM app.artifact_version v JOIN app.artifact_stream s
                      ON s.artifact_stream_id = v.artifact_stream_id
                    WHERE v.execution_id = ?
                    """, UUID.class, currentExecution);
            UUID reviewId = jdbc.queryForObject(
                    "SELECT review_id FROM app.review_records WHERE artifact_version_id = ?",
                    UUID.class, artifactVersion);
            assertEquals(1L, jdbc.queryForObject(
                    "SELECT count(*) FROM app.artifact_version WHERE execution_id = ?",
                    Long.class, currentExecution));
            assertEquals(1L, jdbc.queryForObject(
                    "SELECT count(*) FROM app.execution_publication WHERE execution_id = ?",
                    Long.class, currentExecution));
            assertEquals(1L, jdbc.queryForObject(
                    "SELECT count(*) FROM app.review_records WHERE artifact_version_id = ?",
                    Long.class, artifactVersion));
            assertEquals(artifactVersion, jdbc.queryForObject("""
                    SELECT latest_version_id FROM app.artifact_stream
                    WHERE case_id = ? AND kind = 'parse' AND scope_key = ?
                    """, UUID.class, caseId, "document:" + documentId));

            ReviewService reviews = new ReviewService(jdbc,
                    new CaseService(jdbc, new ObjectMapper().findAndRegisterModules(),
                            new IdempotencyService(jdbc)),
                    new IdempotencyService(jdbc), new ModuleConfirmationService(jdbc),
                    new DraftApprovalService(jdbc));
            boundedTx.execute(status -> {
                reviews.decide(account, reviewId, "approve", 1, "test", "approved after first publish");
                return null;
            });
            assertEquals("approved", jdbc.queryForObject(
                    "SELECT status FROM app.review_records WHERE review_id = ?", String.class, reviewId));

            CyclicBarrier replayStart = new CyclicBarrier(2);
            Future<Map<String, Object>> replayOne = submitAccept(executor, replayStart, boundedTx, callback);
            Future<Map<String, Object>> replayTwo = submitAccept(executor, replayStart, boundedTx, callback);
            replayOne.get(5, TimeUnit.SECONDS);
            replayTwo.get(5, TimeUnit.SECONDS);
            assertEquals(1L, jdbc.queryForObject(
                    "SELECT count(*) FROM app.artifact_version WHERE execution_id = ?",
                    Long.class, currentExecution));
            assertEquals(1L, jdbc.queryForObject(
                    "SELECT count(*) FROM app.execution_publication WHERE execution_id = ?",
                    Long.class, currentExecution));
            assertEquals(1L, jdbc.queryForObject(
                    "SELECT count(*) FROM app.review_records WHERE artifact_version_id = ?",
                    Long.class, artifactVersion));
            assertEquals("approved", jdbc.queryForObject(
                    "SELECT status FROM app.review_records WHERE review_id = ?", String.class, reviewId));
            assertEquals("waiting_review", jdbc.queryForObject(
                    "SELECT status FROM app.tasks WHERE id = ?", String.class, taskId));
        } finally {
            executor.shutdownNow();
        }
    }

    private Future<Map<String, Object>> submitAccept(ExecutorService executor, CyclicBarrier start,
            TransactionTemplate boundedTx, ResultEnvelope callback) {
        return executor.submit(() -> {
            start.await();
            return boundedTx.execute(status -> service.accept(callback));
        });
    }

    private ResultEnvelope envelope(UUID execution, UUID resultId, String content, boolean review) {
        return envelopeStatus(execution, resultId, content, "completed",
                review ? Map.of("human_review_required", true) : Map.of());
    }

    private ResultEnvelope envelopeStatus(UUID execution, UUID resultId, String content, String status,
            Map<String, Object> output) {
        return new ResultEnvelope(execution, taskId, requestId, resultId, 1, "parse-v1", status, "parse",
                content, content == null ? null : hash(content),
                "failed".equals(status) ? "ENGINE_FAILED" : null,
                "failed".equals(status) ? "failed" : null, false, Map.of(), null, "completion-1", output);
    }

    private void addDispatch(UUID execution, UUID resultId, int version) {
        jdbc.update("""
                INSERT INTO app.task_dispatch_outbox(task_id, execution_id, event_type, payload_json)
                VALUES (?, ?, 'task.dispatch', jsonb_build_object('result_id', ?::text, 'result_version', ?::text))
                """, taskId, execution, resultId, version);
    }

    private static String hash(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(64);
            for (byte b : digest) out.append(String.format("%02x", b));
            return out.toString();
        } catch (Exception e) {
            throw new AssertionError(e);
        }
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
