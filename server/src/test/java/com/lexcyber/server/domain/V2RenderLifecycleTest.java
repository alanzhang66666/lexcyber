package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.EngineCapabilitiesClient;
import com.lexcyber.server.engine.EngineResultService;
import com.lexcyber.server.engine.ResultEnvelope;
import com.lexcyber.server.review.ReviewService;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
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
import org.testcontainers.containers.PostgreSQLContainer;

/** Real-Postgres regression coverage for the UUID rendered-draft lifecycle. */
class V2RenderLifecycleTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();
    private static PostgreSQLContainer<?> postgres;

    private JdbcTemplate jdbc;
    private CaseService cases;
    private FactsBaselineService facts;
    private V2LifecycleService lifecycle;
    private ArtifactPublicationService publications;
    private EngineResultService results;
    private ReviewService reviews;
    private TransactionTemplate tx;
    private UUID owner;
    private CaseView caseView;
    private UUID factsVersion;

    @BeforeAll
    static void openDatabase() {
        if (EXTERNAL_JDBC != null && !EXTERNAL_JDBC.isBlank()) return;
        postgres = new PostgreSQLContainer<>("postgres:16.4-alpine")
                .withDatabaseName("lexcyber")
                .withUsername("lex_app")
                .withPassword("lex_app");
        postgres.start();
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
        tx = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        cases = new CaseService(jdbc, MAPPER, new IdempotencyService(jdbc));
        facts = new FactsBaselineService(jdbc, new StalePropagationService(jdbc));
        publications = new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc));
        TaskService tasks = new TaskService(jdbc, MAPPER);
        EngineCapabilitiesClient capabilities = mock(EngineCapabilitiesClient.class);
        when(capabilities.moduleAvailable(anyString())).thenReturn(true);
        when(capabilities.templateAvailable(anyString())).thenReturn(true);
        lifecycle = new V2LifecycleService(jdbc, cases, facts,
                new ModuleConfirmationService(jdbc), new DraftApprovalService(jdbc),
                new CaseArchiveService(jdbc), capabilities, tasks);
        results = new EngineResultService(jdbc, publications, MAPPER);
        reviews = new ReviewService(jdbc, cases, new IdempotencyService(jdbc),
                new ModuleConfirmationService(jdbc), new DraftApprovalService(jdbc));

        owner = insertAccount("render_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12));
        caseView = cases.create(owner, new CaseCreate("render-case", "CN", java.time.LocalDate.of(2026, 9, 6), Map.of()));
        Map<String, Object> draftFacts = lifecycle.createFactsVersion(owner, caseView.id());
        factsVersion = (UUID) draftFacts.get("factsVersionId");
        lifecycle.confirmFactsVersion(owner, caseView.id(), factsVersion, null);
    }

    @Test
    void dispatchCreatesStableUuidDescriptorAndReturnsCorrectStreamIdentity() {
        UUID v1 = insertConfirmedModuleVersion(caseView.id(), "compliance", "{\"rule\":\"v1\"}");
        insertConfirmedModuleVersion(caseView.id(), "conviction", "{\"rule\":\"v1\"}");

        Map<String, Object> first = lifecycle.dispatchDraftRender(owner, caseView.id(), "judgment");
        UUID draftId = (UUID) first.get("draftId");
        assertNotNull(draftId);
        UUID.fromString(draftId.toString());
        assertEquals(draftId, jdbc.queryForObject(
                "SELECT draft_id FROM app.draft_head WHERE draft_id = ?", UUID.class, draftId));

        Map<String, Object> second = lifecycle.dispatchDraftRender(owner, caseView.id(), "judgment");
        assertEquals(draftId, second.get("draftId"));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.case_drafts WHERE case_id = ?::uuid AND render_doc_type = ?",
                Integer.class, caseView.id(), "judgment"));

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> streams = (List<Map<String, Object>>) lifecycle
                .listDraftStreams(owner, caseView.id()).get("items");
        assertEquals(1, streams.size());
        assertEquals(draftId, streams.get(0).get("draftId"));
        assertEquals("judgment", streams.get(0).get("docType"));
        assertEquals(v1, jdbc.queryForObject(
                "SELECT confirmed_version_id FROM app.module_head WHERE case_id = ?::uuid AND module = 'compliance'",
                UUID.class, caseView.id()));
        assertEquals(Boolean.FALSE, jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id = ?::uuid AND module = 'compliance'",
                Boolean.class, caseView.id()));
    }

    @Test
    void dispatchRequiresCaseDateBeforeCreatingTaskOrDraft() {
        jdbc.update("UPDATE app.cases SET as_of_date = NULL WHERE id = ?::uuid", caseView.id());
        ApiException error = assertThrows(ApiException.class,
                () -> lifecycle.dispatchModuleExecution(owner, caseView.id(), "compliance"));
        assertEquals("AS_OF_DATE_REQUIRED", error.code());
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.tasks WHERE case_id = ?::uuid", Integer.class, caseView.id()));
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.task_dispatch_outbox WHERE task_id IN "
                        + "(SELECT id FROM app.tasks WHERE case_id = ?::uuid)", Integer.class, caseView.id()));
    }

    @Test
    void sentencingRequiresEffectiveConvictionAndFreezesItsArtifactDependency() throws Exception {
        ApiException missingConviction = assertThrows(ApiException.class,
                () -> lifecycle.dispatchModuleExecution(owner, caseView.id(), "sentencing"));
        assertEquals("MODULE_NOT_CONFIRMED", missingConviction.code());
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.task_dispatch_outbox WHERE task_id IN "
                        + "(SELECT id FROM app.tasks WHERE case_id = ?::uuid)", Integer.class, caseView.id()));

        UUID convictionV1 = insertConfirmedModuleVersion(caseView.id(), "conviction", "{\"rule\":\"v1\"}");
        Map<String, Object> dispatched = lifecycle.dispatchModuleExecution(owner, caseView.id(), "sentencing");
        UUID taskId = (UUID) dispatched.get("taskId");
        Map<String, Object> task = jdbc.queryForMap(
                "SELECT execution_id, request_id FROM app.tasks WHERE id = ?", taskId);
        UUID executionId = (UUID) task.get("execution_id");
        UUID requestId = (UUID) task.get("request_id");
        JsonNode dispatch = MAPPER.readTree(jdbc.queryForObject(
                "SELECT payload_json::text FROM app.task_dispatch_outbox WHERE task_id = ? AND execution_id = ?",
                String.class, taskId, executionId));
        assertEquals("2026-09-06", dispatch.get("metadata").get("asOfDate").asText());
        assertEquals(convictionV1.toString(), dispatch.get("metadata").get("artifactVersions")
                .get("conviction").asText());

        String content = MAPPER.writeValueAsString(Map.of(
                "schema_version", "sentencing.v2", "status", "calculated",
                "input_validation", validInputValidation(),
                "dependency_snapshot", Map.of("as_of_date", "2026-09-06", "facts_version_id", factsVersion.toString(),
                        "artifacts", List.of(Map.of("module", "conviction",
                                "artifactVersionId", convictionV1.toString()))),
                "results", List.of()));
        JsonNode dispatchIdentity = dispatch;
        ResultEnvelope callback = new ResultEnvelope(executionId, taskId, requestId,
                UUID.fromString(dispatchIdentity.get("result_id").asText()),
                dispatchIdentity.get("result_version").asInt(), "sentencing.v2", "completed",
                "sentencing", content, FactsBaselineService.sha256(content), null, null, false,
                null, null, "sentencing-v1", Map.of("human_review_required", true));
        // The frozen conviction is allowed to complete after the upstream has
        // advanced; confirmation, rather than callback delivery, rejects it.
        publications.publish(new ArtifactPublicationService.PublishRequest(
                caseView.id(), "conviction", "module:conviction", "module.v2", "calculated",
                "{\"rule\":\"v2\"}", "[]", "{}", factsVersion, List.of(), List.of(),
                null, null, "conviction-v2"));
        tx.execute(status -> {
            results.accept(callback);
            return null;
        });

        UUID sentencingV1 = jdbc.queryForObject("""
                SELECT v.artifact_version_id FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                WHERE s.case_id = ?::uuid AND s.kind = 'sentencing'
                  AND s.scope_key = 'module:sentencing'
                """, UUID.class, caseView.id());
        assertEquals(convictionV1, jdbc.queryForObject(
                "SELECT depends_on_artifact_version_id FROM app.artifact_artifact_dependency "
                        + "WHERE artifact_version_id = ?", UUID.class, sentencingV1));

        Map<String, Object> opened = lifecycle.openReview(owner, sentencingV1, "review sentencing");
        UUID reviewId = (UUID) opened.get("reviewId");
        ApiException stale = assertThrows(ApiException.class, () -> tx.execute(status -> {
            reviews.decide(owner, reviewId, "approve", 1, "owner", "approve");
            return null;
        }));
        assertEquals("MODULE_NOT_CONFIRMED", stale.code());
        assertEquals("pending", jdbc.queryForObject(
                "SELECT status FROM app.review_records WHERE review_id = ?", String.class, reviewId));
    }

    @Test
    void convictionChargeRequestsAreFrozenInOutboxAndRetry() throws Exception {
        Map<String, Object> requested = new java.util.LinkedHashMap<>();
        requested.put("requestedCharge", "明确请求的原始名称");
        requested.put("chargeKey", "explicit.key");
        Map<String, Object> dispatched = lifecycle.dispatchModuleExecution(owner, caseView.id(), "conviction",
                Map.of("requestedCharges", List.of(requested)));
        UUID taskId = (UUID) dispatched.get("taskId");
        UUID executionId = (UUID) dispatched.get("executionId");
        requested.put("chargeKey", "caller.changed.after.dispatch");
        JsonNode original = MAPPER.readTree(jdbc.queryForObject(
                "SELECT payload_json::text FROM app.task_dispatch_outbox WHERE task_id=? AND execution_id=?",
                String.class, taskId, executionId));
        assertEquals("explicit.key", original.path("metadata").path("requestedCharges").get(0).path("chargeKey").asText());
        assertEquals("明确请求的原始名称", original.path("metadata").path("requestedCharges").get(0).path("requestedCharge").asText());
        jdbc.update("UPDATE app.tasks SET status='failed' WHERE id=?", taskId);
        EngineCapabilitiesClient caps = mock(EngineCapabilitiesClient.class);
        when(caps.moduleAvailable(anyString())).thenReturn(true);
        TaskView retry = tx.execute(status -> new TaskService(jdbc, MAPPER, false, caps).retry(taskId));
        JsonNode retried = MAPPER.readTree(jdbc.queryForObject(
                "SELECT payload_json::text FROM app.task_dispatch_outbox WHERE task_id=? AND execution_id=?",
                String.class, taskId, retry.executionId()));
        assertEquals(original.path("metadata"), retried.path("metadata"));
        assertEquals(original.path("input_hash"), retried.path("input_hash"));
        assertEquals(original.path("input_snapshot_ref"), retried.path("input_snapshot_ref"));
    }

    @Test
    void invalidChargeRequestDoesNotCreateATask() {
        ApiException error = assertThrows(ApiException.class,
                () -> lifecycle.dispatchModuleExecution(owner, caseView.id(), "conviction",
                        Map.of("requestedCharges", "invalid-array")));
        assertEquals("INVALID_REQUESTED_CHARGES", error.code());
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.tasks WHERE case_id=?::uuid",
                Integer.class, caseView.id()));
    }

    @Test
    void callbackUsesFrozenV1DependenciesAndApprovalRejectsStaleUpstream() throws Exception {
        UUID complianceV1 = insertConfirmedModuleVersion(caseView.id(), "compliance", "{\"rule\":\"v1\"}");
        Map<String, Object> dispatched = lifecycle.dispatchDraftRender(owner, caseView.id(), "judgment");
        UUID taskId = (UUID) dispatched.get("taskId");
        UUID draftId = (UUID) dispatched.get("draftId");
        Map<String, Object> task = jdbc.queryForMap(
                "SELECT execution_id, request_id FROM app.tasks WHERE id = ?", taskId);
        UUID executionId = (UUID) task.get("execution_id");
        UUID requestId = (UUID) task.get("request_id");
        JsonNode dispatch = MAPPER.readTree(jdbc.queryForObject(
                "SELECT payload_json::text FROM app.task_dispatch_outbox WHERE task_id = ? AND execution_id = ?",
                String.class, taskId, executionId));
        UUID resultId = UUID.fromString(dispatch.get("result_id").asText());
        int resultVersion = dispatch.get("result_version").asInt();
        assertEquals("facts_version:" + factsVersion, dispatch.get("input_snapshot_ref").asText());
        assertEquals(complianceV1.toString(), dispatch.get("metadata").get("artifactVersions")
                .get("compliance").asText());

        String content = MAPPER.writeValueAsString(Map.of(
                "schema_version", "draft.v2",
                "status", "calculated",
                "input_validation", validInputValidation(),
                "dependency_snapshot", Map.of(
                        "as_of_date", "2026-09-06",
                        "facts_version_id", factsVersion.toString(),
                        "artifacts", List.of(Map.of(
                                "module", "compliance", "artifactVersionId", complianceV1.toString()))),
                "body", "rendered with frozen V1"));
        ResultEnvelope callback = new ResultEnvelope(executionId, taskId, requestId, resultId,
                resultVersion, "draft.v2", "completed", "rendered", content,
                FactsBaselineService.sha256(content), null, null, false, null, null,
                "render-v1", Map.of("human_review_required", true));
        tx.execute(status -> {
            results.accept(callback);
            return null;
        });

        UUID renderedVersion = jdbc.queryForObject("""
                SELECT v.artifact_version_id FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                WHERE s.case_id = ?::uuid AND s.kind = 'draft' AND s.scope_key = ?
                """, UUID.class, caseView.id(), "draft:" + draftId);
        assertEquals(complianceV1, jdbc.queryForObject(
                "SELECT depends_on_artifact_version_id FROM app.artifact_artifact_dependency WHERE artifact_version_id = ?",
                UUID.class, renderedVersion));
        assertEquals(complianceV1, jdbc.queryForObject("""
                SELECT (dependency_snapshot->'artifacts'->0->>'artifactVersionId')::uuid
                FROM app.artifact_version WHERE artifact_version_id = ?
                """, UUID.class, renderedVersion));

        // Publish after the callback, then verify the normal stale approval path.
        publications.publish(new ArtifactPublicationService.PublishRequest(
                caseView.id(), "compliance", "module:compliance", "module.v2", "calculated",
                "{\"rule\":\"v2\"}", "[]", "{}", factsVersion, List.of(), List.of(),
                null, null, "upstream-v2"));
        assertEquals(Boolean.TRUE, jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id = ?::uuid AND module = 'compliance'",
                Boolean.class, caseView.id()));
        Map<String, Object> opened = lifecycle.openReview(owner, renderedVersion, "check frozen dependency");
        UUID reviewId = (UUID) opened.get("reviewId");
        ApiException stale = assertThrows(ApiException.class, () -> tx.execute(status -> {
            reviews.decide(owner, reviewId, "approve", 1, "owner", "approve");
            return null;
        }));
        assertEquals("DEPENDENCY_STALE", stale.code());
        assertEquals("pending", jdbc.queryForObject(
                "SELECT status FROM app.review_records WHERE review_id = ?", String.class, reviewId));
        assertTrue(jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.artifact_artifact_dependency WHERE artifact_version_id = ?",
                Integer.class, renderedVersion) > 0);
    }

    @Test
    void approvalWaitsForUpstreamPublishBeforeCheckingFrozenDependency() throws Exception {
        RenderReviewFixture fixture = createPendingRenderReview();
        TransactionTemplate boundedTx = new TransactionTemplate(
                new DataSourceTransactionManager(jdbc.getDataSource()));
        boundedTx.setTimeout(10);
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<ApiException> approval = null;
        try {
            Future<ApiException> future = boundedTx.execute(status -> {
                jdbc.queryForObject("""
                        SELECT artifact_stream_id FROM app.artifact_stream
                        WHERE case_id = ?::uuid AND kind = 'compliance' AND scope_key = 'module:compliance'
                        FOR UPDATE
                        """, UUID.class, caseView.id());
                CountDownLatch started = new CountDownLatch(1);
                Future<ApiException> submitted = executor.submit(() -> {
                    started.countDown();
                    try {
                        boundedTx.execute(inner -> {
                            reviews.decide(owner, fixture.reviewId(), "approve", 1, "owner", "approve");
                            return null;
                        });
                        return null;
                    } catch (ApiException failure) {
                        return failure;
                    }
                });
                try {
                    assertTrue(started.await(5, TimeUnit.SECONDS));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("approval start interrupted", interrupted);
                }
                assertThrows(TimeoutException.class, () -> submitted.get(200, TimeUnit.MILLISECONDS));
                publications.publish(new ArtifactPublicationService.PublishRequest(
                        caseView.id(), "compliance", "module:compliance", "module.v2", "calculated",
                        "{\"rule\":\"v2\"}", "[]", "{}", factsVersion, List.of(), List.of(),
                        null, null, "upstream-v2-concurrent"));
                return submitted;
            });
            approval = future;
            ApiException stale = approval.get(5, TimeUnit.SECONDS);
            assertNotNull(stale, "approval unexpectedly succeeded before dependency publication");
            assertEquals("DEPENDENCY_STALE", stale.code());
            assertEquals("pending", jdbc.queryForObject(
                    "SELECT status FROM app.review_records WHERE review_id = ?", String.class, fixture.reviewId()));
        } finally {
            executor.shutdownNow();
            if (approval != null) approval.cancel(true);
        }
    }

    private RenderReviewFixture createPendingRenderReview() throws Exception {
        UUID complianceV1 = insertConfirmedModuleVersion(caseView.id(), "compliance", "{\"rule\":\"v1\"}");
        Map<String, Object> dispatched = lifecycle.dispatchDraftRender(owner, caseView.id(), "judgment");
        UUID taskId = (UUID) dispatched.get("taskId");
        UUID draftId = (UUID) dispatched.get("draftId");
        Map<String, Object> task = jdbc.queryForMap(
                "SELECT execution_id, request_id FROM app.tasks WHERE id = ?", taskId);
        UUID executionId = (UUID) task.get("execution_id");
        UUID requestId = (UUID) task.get("request_id");
        JsonNode dispatch = MAPPER.readTree(jdbc.queryForObject(
                "SELECT payload_json::text FROM app.task_dispatch_outbox WHERE task_id = ? AND execution_id = ?",
                String.class, taskId, executionId));
        String content = MAPPER.writeValueAsString(Map.of(
                "schema_version", "draft.v2", "status", "calculated",
                "input_validation", validInputValidation(),
                "dependency_snapshot", Map.of("as_of_date", "2026-09-06", "facts_version_id", factsVersion.toString(),
                        "artifacts", List.of(Map.of("module", "compliance", "artifactVersionId", complianceV1.toString()))),
                "body", "rendered with frozen V1"));
        ResultEnvelope callback = new ResultEnvelope(executionId, taskId, requestId,
                UUID.fromString(dispatch.get("result_id").asText()), dispatch.get("result_version").asInt(),
                "draft.v2", "completed", "rendered", content, FactsBaselineService.sha256(content),
                null, null, false, null, null, "render-concurrent", Map.of("human_review_required", true));
        tx.execute(status -> { results.accept(callback); return null; });
        UUID renderedVersion = jdbc.queryForObject("""
                SELECT v.artifact_version_id FROM app.artifact_version v
                JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
                WHERE s.case_id = ?::uuid AND s.kind = 'draft' AND s.scope_key = ?
                """, UUID.class, caseView.id(), "draft:" + draftId);
        Map<String, Object> opened = lifecycle.openReview(owner, renderedVersion, "concurrency");
        return new RenderReviewFixture((UUID) opened.get("reviewId"));
    }

    private record RenderReviewFixture(UUID reviewId) {}

    private Map<String, Object> validInputValidation() {
        return Map.of("schema_version", "case.input-validation.v1", "status", "verified",
                "checks", List.of(), "blockers", List.of());
    }

    private UUID insertConfirmedModuleVersion(String caseId, String module, String payload) {
        UUID streamId = UUID.randomUUID();
        UUID versionId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                VALUES (?, ?::uuid, ?, ?, 2)
                """, streamId, caseId, module, "module:" + module);
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, 'module.v1', 'calculated', ?::jsonb, '{}'::jsonb, ?)
                """, versionId, streamId, payload, "hash-" + versionId);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                versionId, streamId);
        jdbc.update("""
                INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale)
                VALUES (?::uuid, ?, ?, ?, false)
                """, caseId, module, streamId, versionId);
        return versionId;
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
        } else {
            dataSource.setUrl(postgres.getJdbcUrl());
            dataSource.setUsername(postgres.getUsername());
            dataSource.setPassword(postgres.getPassword());
        }
        return dataSource;
    }

    private static String envOr(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
