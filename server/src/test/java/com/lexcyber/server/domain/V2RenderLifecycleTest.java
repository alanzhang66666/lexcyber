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
        when(capabilities.templateAvailable(anyString())).thenReturn(true);
        lifecycle = new V2LifecycleService(jdbc, cases, facts,
                new ModuleConfirmationService(jdbc), new DraftApprovalService(jdbc),
                new CaseArchiveService(jdbc), capabilities, tasks);
        results = new EngineResultService(jdbc, publications, MAPPER);
        reviews = new ReviewService(jdbc, cases, new IdempotencyService(jdbc),
                new ModuleConfirmationService(jdbc), new DraftApprovalService(jdbc));

        owner = insertAccount("render_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12));
        caseView = cases.create(owner, new CaseCreate("render-case", "CN", null, Map.of()));
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

        // A newer upstream version is published after dispatch. The callback must
        // still bind the exact V1 id carried by its frozen dependency snapshot.
        publications.publish(new ArtifactPublicationService.PublishRequest(
                caseView.id(), "compliance", "module:compliance", "module.v2", "calculated",
                "{\"rule\":\"v2\"}", "[]", "{}", factsVersion, List.of(), List.of(),
                null, null, "upstream-v2"));
        assertEquals(Boolean.TRUE, jdbc.queryForObject(
                "SELECT stale FROM app.module_head WHERE case_id = ?::uuid AND module = 'compliance'",
                Boolean.class, caseView.id()));

        String content = MAPPER.writeValueAsString(Map.of(
                "schema_version", "draft.v2",
                "status", "calculated",
                "dependency_snapshot", Map.of(
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

        Map<String, Object> opened = lifecycle.openReview(owner, renderedVersion, "check frozen dependency");
        ApiException stale = assertThrows(ApiException.class, () -> tx.execute(status -> {
            reviews.decide(owner, (UUID) opened.get("reviewId"), "approve", 1, "owner", "approve");
            return null;
        }));
        assertEquals("DEPENDENCY_STALE", stale.code());
        assertEquals("pending", jdbc.queryForObject(
                "SELECT status FROM app.review_records WHERE review_id = ?", String.class, opened.get("reviewId")));
        assertTrue(jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.artifact_artifact_dependency WHERE artifact_version_id = ?",
                Integer.class, renderedVersion) > 0);
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
