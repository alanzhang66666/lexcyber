package com.lexcyber.server.review;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.ArtifactPublicationService;
import com.lexcyber.server.domain.CaseCreate;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
import com.lexcyber.server.domain.DraftApprovalService;
import com.lexcyber.server.domain.DraftCreate;
import com.lexcyber.server.domain.DraftService;
import com.lexcyber.server.domain.IdempotencyService;
import com.lexcyber.server.domain.ModuleConfirmationService;
import com.lexcyber.server.domain.ModuleStateService;
import com.lexcyber.server.domain.ModuleStateUpdate;
import com.lexcyber.server.domain.StalePropagationService;
import java.time.LocalDate;
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
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.testcontainers.containers.PostgreSQLContainer;

/** Owner-scoped review SQL. Uses Testcontainers Postgres, or TEST_JDBC_URL when Docker-in-Docker is unavailable. */
class ReviewServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static final LocalDate FIXED_AS_OF_DATE = LocalDate.of(2026, 9, 6);
    private static PostgreSQLContainer<?> postgres;

    private ReviewService reviews;
    private JdbcTemplate jdbc;
    private UUID alice;
    private UUID bob;
    private String aliceName;
    private String bobName;
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
        jdbc = new JdbcTemplate(dataSource);
        CaseService cases = new CaseService(jdbc, new ObjectMapper().findAndRegisterModules(), new IdempotencyService(jdbc));
        reviews = new ReviewService(jdbc, cases, new IdempotencyService(jdbc),
                new ModuleConfirmationService(jdbc), new DraftApprovalService(jdbc));
        aliceName = "alice_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        bobName = "bob_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        alice = insertAccount(aliceName);
        bob = insertAccount(bobName);
        aliceCase = cases.create(alice, new CaseCreate("alice-case", "CN", FIXED_AS_OF_DATE, Map.of()));
        bobCase = cases.create(bob, new CaseCreate("bob-case", "CN", FIXED_AS_OF_DATE, Map.of()));
    }

    @Test
    void ownerSeesOwnReviewWithCaseIdAndOthersAreHidden() {
        UUID aliceReview = insertReview(aliceCase.id(), "parse", "pending");
        UUID bobReview = insertReview(bobCase.id(), "parse", "pending");

        Map<String, Object> page = reviews.list(alice, "pending", 0, 20);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> items = (List<Map<String, Object>>) page.get("items");
        assertEquals(1L, page.get("total"));
        assertEquals(1, items.size());
        assertEquals(aliceReview, items.get(0).get("id"));
        assertEquals(aliceCase.id(), items.get(0).get("caseId"));
        assertEquals("parse", items.get(0).get("module"));

        Map<String, Object> owned = reviews.get(alice, aliceReview);
        assertEquals(aliceCase.id(), owned.get("caseId"));
        assertEquals(1, owned.get("resultVersion"));
        assertEquals("parse", owned.get("module"));

        ApiException hidden = assertThrows(ApiException.class, () -> reviews.get(alice, bobReview));
        assertEquals(HttpStatus.NOT_FOUND, hidden.status());
        assertEquals("REVIEW_NOT_FOUND", hidden.code());

        Map<String, Object> bobPage = reviews.list(bob, null, 0, 20);
        assertEquals(1L, bobPage.get("total"));
        ApiException missing = assertThrows(ApiException.class, () -> reviews.get(alice, UUID.randomUUID()));
        assertEquals("REVIEW_NOT_FOUND", missing.code());
    }

    @Test
    void decideKeepsVersionBindingAndDoesNotLeakOtherCases() {
        UUID aliceReview = insertReview(aliceCase.id(), "parse", "pending");
        UUID bobReview = insertReview(bobCase.id(), "parse", "pending");

        ApiException hidden = assertThrows(ApiException.class,
                () -> reviews.decide(alice, bobReview, "approve", 1, "alice", "nope"));
        assertEquals("REVIEW_NOT_FOUND", hidden.code());
        assertEquals("pending", jdbc.queryForObject("SELECT status FROM app.review_records WHERE review_id=?", String.class, bobReview));

        ResponseStatusException wrongVersion = assertThrows(ResponseStatusException.class,
                () -> reviews.decide(alice, aliceReview, "approve", 2, "alice", "wrong version"));
        assertEquals(HttpStatus.CONFLICT, wrongVersion.getStatusCode());
        assertEquals("pending", jdbc.queryForObject("SELECT status FROM app.review_records WHERE review_id=?", String.class, aliceReview));

        Map<String, Object> approved = reviews.decide(alice, aliceReview, "approve", 1, "alice", "ok");
        assertEquals("approved", approved.get("status"));
        assertEquals("approve", approved.get("decision"));
        assertEquals(aliceCase.id(), approved.get("caseId"));
        assertEquals(aliceName, approved.get("actor"));
        assertEquals(Boolean.TRUE, approved.get("authenticated"));

        ResponseStatusException again = assertThrows(ResponseStatusException.class,
                () -> reviews.decide(alice, aliceReview, "reject", 1, "alice", "late"));
        assertEquals(HttpStatus.CONFLICT, again.getStatusCode());
    }

    @Test
    void moduleDerivesFromStreamKindAndCanFilter() {
        UUID parseReview = insertReview(aliceCase.id(), "parse", "pending");
        UUID sentencingReview = insertReview(aliceCase.id(), "sentencing", "pending");
        UUID complianceReview = insertReview(aliceCase.id(), "compliance", "pending");
        UUID convictionReview = insertReview(aliceCase.id(), "conviction", "pending");

        assertEquals("parse", reviews.get(alice, parseReview).get("module"));
        assertEquals("sentencing", reviews.get(alice, sentencingReview).get("module"));
        assertEquals("compliance", reviews.get(alice, complianceReview).get("module"));
        assertEquals("conviction", reviews.get(alice, convictionReview).get("module"));

        Map<String, Object> parsePage = reviews.list(alice, null, "parse", 0, 20);
        assertEquals(1L, parsePage.get("total"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> parseItems = (List<Map<String, Object>>) parsePage.get("items");
        assertEquals(parseReview, parseItems.get(0).get("id"));

        assertEquals(1L, reviews.list(alice, null, "compliance", 0, 20).get("total"));
        assertEquals(1L, reviews.list(alice, null, "conviction", 0, 20).get("total"));
    }

    @Test
    void draftApprovalUsesHeadUuidWhenScopeKeyIsNull() {
        DraftService drafts = new DraftService(jdbc,
                new CaseService(jdbc, new ObjectMapper().findAndRegisterModules(), new IdempotencyService(jdbc)),
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc)));
        var draft = drafts.create(alice, aliceCase.id(), new DraftCreate("judgment", "body"));
        UUID draftId = UUID.fromString(draft.id());
        Map<String, Object> opened = reviews.open(alice, aliceCase.id(),
                new ReviewOpen("draft", draft.id(), null, null, null, 1, null, null));
        jdbc.update("UPDATE app.artifact_stream SET scope_key = 'legacy-scope' WHERE kind = 'draft' AND case_id = ?::uuid", aliceCase.id());
        Map<String, Object> shown = reviews.get(alice, (UUID) opened.get("id"));
        assertEquals(draftId.toString(), shown.get("draftId"));

        Map<String, Object> decided = reviews.decide(alice, (UUID) opened.get("id"),
                "approve", 1, aliceName, "ok");
        assertEquals("approved", decided.get("status"));
        assertEquals(draftId, jdbc.queryForObject(
                "SELECT draft_id FROM app.draft_head WHERE draft_id = ?", UUID.class, draftId));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.draft_head WHERE draft_id = ? AND approved_version_id IS NOT NULL",
                Integer.class, draftId));
    }

    @Test
    void draftV2StringDependencyAndStaleUpstreamRollBackDecision() {
        DraftService drafts = new DraftService(jdbc,
                new CaseService(jdbc, new ObjectMapper().findAndRegisterModules(), new IdempotencyService(jdbc)),
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc)));
        var draft = drafts.create(alice, aliceCase.id(), new DraftCreate("judgment", "body"));
        UUID draftId = UUID.fromString(draft.id());
        UUID draftVersion = jdbc.queryForObject(
                "SELECT latest_version_id FROM app.artifact_stream WHERE kind='draft' AND case_id=?::uuid",
                UUID.class, aliceCase.id());
        UUID upstream = insertConfirmedModuleVersion(aliceCase.id(), "compliance");
        jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?)",
                draftVersion, upstream);
        jdbc.update("UPDATE app.artifact_version SET schema_version = 'draft.v2', dependency_snapshot = '{\"as_of_date\":\"2026-09-06\",\"artifacts\":[\"compliance\"]}'::jsonb WHERE artifact_version_id = ?", draftVersion);
        Map<String, Object> opened = reviews.open(alice, aliceCase.id(),
                new ReviewOpen("draft", draft.id(), null, null, null, 1, null, null));

        TransactionTemplate tx = new TransactionTemplate(new DataSourceTransactionManager(jdbc.getDataSource()));
        assertThrows(ApiException.class, () -> tx.execute(status -> {
            reviews.decide(alice, (UUID) opened.get("id"), "approve", 1, aliceName, "stale");
            return null;
        }));
        assertEquals("pending", jdbc.queryForObject("SELECT status FROM app.review_records WHERE review_id=?",
                String.class, opened.get("id")));

        jdbc.update("UPDATE app.module_head SET stale = true, stale_reason = 'dependency_changed' WHERE case_id = ?::uuid AND module = 'compliance'",
                aliceCase.id());
        assertThrows(ApiException.class, () -> tx.execute(status -> {
            reviews.decide(alice, (UUID) opened.get("id"), "approve", 1, aliceName, "stale");
            return null;
        }));
        assertEquals("pending", jdbc.queryForObject("SELECT status FROM app.review_records WHERE review_id=?",
                String.class, opened.get("id")));
    }

    @Test
    void openOnModuleThenArchiveIsGone() {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        CaseService cases = new CaseService(jdbc, mapper, new IdempotencyService(jdbc));
        ModuleStateService modules = new ModuleStateService(jdbc, mapper, cases,
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc)),
                new ModuleConfirmationService(jdbc), true);
        modules.replace(alice, aliceCase.id(), "conviction",
                new ModuleStateUpdate("unknown", Map.of("note", "shell"), null, 0));

        Map<String, Object> opened = reviews.open(alice, aliceCase.id(),
                new ReviewOpen("conviction", null, null, "conviction", 1, null, null, null));
        assertEquals(aliceCase.id(), opened.get("caseId"));
        assertEquals("pending", opened.get("status"));
        assertEquals("conviction", opened.get("module"));
        assertEquals("conviction", opened.get("moduleState"));
        assertEquals(1, opened.get("moduleVersion"));
        assertEquals("open", opened.get("archiveStatus"));
        assertEquals(null, opened.get("taskId"));

        UUID reviewId = (UUID) opened.get("id");
        ApiException hidden = assertThrows(ApiException.class, () -> reviews.get(bob, reviewId));
        assertEquals("REVIEW_NOT_FOUND", hidden.code());

        // /v1 单条复核归档已移除（归档为案件级）：410 GONE
        ApiException gone = assertThrows(ApiException.class, () -> reviews.archive(alice, reviewId));
        assertEquals(HttpStatus.GONE, gone.status());
        assertEquals("REVIEW_ARCHIVE_REMOVED", gone.code());
        ApiException goneForBob = assertThrows(ApiException.class, () -> reviews.archive(bob, reviewId));
        assertEquals(HttpStatus.GONE, goneForBob.status());

        // archiveStatus 参数忽略：两种取值都返回全部复核
        assertEquals(1L, reviews.list(alice, null, null, "open", 0, 20).get("total"));
        assertEquals(1L, reviews.list(alice, null, null, "archived", 0, 20).get("total"));

        Map<String, Object> decided = reviews.decide(alice, reviewId, "approve", 1, "alice", "ok");
        assertEquals("approved", decided.get("status"));
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.tasks WHERE case_id=?::uuid", Integer.class, aliceCase.id()));
    }

    /** 新模型下复核绑定 artifact_version：造 stream + version + review。 */
    private UUID insertReview(String caseId, String kind, String reviewStatus) {
        UUID streamId = UUID.randomUUID();
        String scope = "module".equals(kind) ? "module:" + kind
                : ("parse".equals(kind) ? "document:" + UUID.randomUUID()
                : kind + ":" + UUID.randomUUID());
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                VALUES (?, ?::uuid, ?, ?, 2)
                """, streamId, caseId, kind, scope);
        UUID versionId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, 'test.v1', 'calculated', '{}'::jsonb, '{}'::jsonb, 'h')
                """, versionId, streamId);
        jdbc.update("""
                UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?
                """, versionId, streamId);
        if (List.of("compliance", "conviction", "sentencing").contains(kind)) {
            jdbc.update("""
                    INSERT INTO app.module_head(case_id, module, artifact_stream_id)
                    VALUES (?::uuid, ?, ?) ON CONFLICT (case_id, module) DO NOTHING
                    """, caseId, kind, streamId);
        }
        UUID reviewId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.review_records(review_id, artifact_version_id, case_id, status, actor_id)
                VALUES (?, ?, ?::uuid, ?, ?)
                """, reviewId, versionId, caseId, reviewStatus, alice);
        return reviewId;
    }

    private UUID insertConfirmedModuleVersion(String caseId, String module) {
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
                VALUES (?, ?, 1, 'test.v1', 'calculated', '{}'::jsonb, '{}'::jsonb, 'upstream')
                """, versionId, streamId);
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
