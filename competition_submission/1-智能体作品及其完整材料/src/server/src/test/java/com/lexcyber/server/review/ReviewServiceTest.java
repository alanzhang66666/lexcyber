package com.lexcyber.server.review;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.CaseCreate;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
import com.lexcyber.server.domain.ModuleStateService;
import com.lexcyber.server.domain.ModuleStateUpdate;
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
import org.springframework.web.server.ResponseStatusException;
import org.testcontainers.containers.PostgreSQLContainer;

/** Owner-scoped review SQL. Uses Testcontainers Postgres, or TEST_JDBC_URL when Docker-in-Docker is unavailable. */
class ReviewServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private ReviewService reviews;
    private JdbcTemplate jdbc;
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
        jdbc = new JdbcTemplate(dataSource);
        CaseService cases = new CaseService(jdbc, new ObjectMapper().findAndRegisterModules());
        reviews = new ReviewService(jdbc, cases);
        alice = insertAccount("alice_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        bob = insertAccount("bob_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        aliceCase = cases.create(alice, new CaseCreate("alice-case", "CN", null, Map.of()));
        bobCase = cases.create(bob, new CaseCreate("bob-case", "CN", null, Map.of()));
    }

    @Test
    void ownerSeesOwnReviewWithCaseIdAndOthersAreHidden() {
        UUID aliceReview = insertReview(aliceCase.id(), "waiting_review", "pending");
        UUID bobReview = insertReview(bobCase.id(), "waiting_review", "pending");
        insertReview("", "waiting_review", "pending");

        Map<String, Object> page = reviews.list(alice, "pending", 0, 20);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> items = (List<Map<String, Object>>) page.get("items");
        assertEquals(1L, page.get("total"));
        assertEquals(1, items.size());
        assertEquals(aliceReview, items.get(0).get("id"));
        assertEquals(aliceCase.id(), items.get(0).get("caseId"));
        assertEquals("task", items.get(0).get("module"));

        Map<String, Object> owned = reviews.get(alice, aliceReview);
        assertEquals(aliceCase.id(), owned.get("caseId"));
        assertEquals(1, owned.get("resultVersion"));
        assertEquals("task", owned.get("module"));

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
        UUID aliceReview = insertReview(aliceCase.id(), "waiting_review", "pending");
        UUID bobReview = insertReview(bobCase.id(), "waiting_review", "pending");

        ApiException hidden = assertThrows(ApiException.class,
                () -> reviews.decide(alice, bobReview, "approve", 1, "alice", "nope"));
        assertEquals("REVIEW_NOT_FOUND", hidden.code());
        assertEquals("pending", jdbc.queryForObject("SELECT status FROM app.review_records WHERE id=?", String.class, bobReview));

        ResponseStatusException stale = assertThrows(ResponseStatusException.class,
                () -> reviews.decide(alice, aliceReview, "approve", 9, "alice", "stale"));
        assertEquals(HttpStatus.CONFLICT, stale.getStatusCode());
        assertEquals("pending", jdbc.queryForObject("SELECT status FROM app.review_records WHERE id=?", String.class, aliceReview));

        Map<String, Object> approved = reviews.decide(alice, aliceReview, "approve", 1, "alice", "ok");
        assertEquals("approved", approved.get("status"));
        assertEquals("approve", approved.get("decision"));
        assertEquals(aliceCase.id(), approved.get("caseId"));
        assertEquals("alice", approved.get("actor"));
        assertEquals(Boolean.TRUE, approved.get("authenticated"));

        ResponseStatusException again = assertThrows(ResponseStatusException.class,
                () -> reviews.decide(alice, aliceReview, "reject", 1, "alice", "late"));
        assertEquals(HttpStatus.CONFLICT, again.getStatusCode());
    }

    @Test
    void moduleIsMappedFromMetadataAndCanFilter() {
        UUID parseReview = insertReview(aliceCase.id(), "waiting_review", "pending",
                "{\"taskType\":\"document.parse\"}");
        UUID sentencingReview = insertReview(aliceCase.id(), "waiting_review", "pending",
                "{\"taskType\":\"sentencing.calculate\"}");
        UUID explicit = insertReview(aliceCase.id(), "waiting_review", "pending",
                "{\"module\":\"compliance\",\"taskType\":\"document.parse\"}");

        assertEquals("parse", reviews.get(alice, parseReview).get("module"));
        assertEquals("sentencing", reviews.get(alice, sentencingReview).get("module"));
        assertEquals("compliance", reviews.get(alice, explicit).get("module"));

        Map<String, Object> parsePage = reviews.list(alice, null, "parse", 0, 20);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> parseItems = (List<Map<String, Object>>) parsePage.get("items");
        assertEquals(1L, parsePage.get("total"));
        assertEquals(parseReview, parseItems.get(0).get("id"));

        Map<String, Object> compliancePage = reviews.list(alice, null, "compliance", 0, 20);
        assertEquals(1L, compliancePage.get("total"));

        UUID analyze = insertReview(aliceCase.id(), "waiting_review", "pending",
                "{\"taskType\":\"compliance.analyze\"}");
        UUID convictionAnalyze = insertReview(aliceCase.id(), "waiting_review", "pending",
                "{\"taskType\":\"conviction.analyze\"}");
        assertEquals("compliance", reviews.get(alice, analyze).get("module"));
        assertEquals("conviction", reviews.get(alice, convictionAnalyze).get("module"));
    }

    @Test
    void openWithoutTaskThenArchiveStaysOwnerScoped() {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        CaseService cases = new CaseService(jdbc, mapper);
        ModuleStateService modules = new ModuleStateService(jdbc, mapper, cases);
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
        ApiException hiddenArchive = assertThrows(ApiException.class, () -> reviews.archive(bob, reviewId));
        assertEquals("REVIEW_NOT_FOUND", hiddenArchive.code());

        Map<String, Object> archived = reviews.archive(alice, reviewId);
        assertEquals("archived", archived.get("archiveStatus"));
        assertEquals("pending", archived.get("status"));

        Map<String, Object> openPage = reviews.list(alice, null, null, "open", 0, 20);
        assertEquals(0L, openPage.get("total"));
        Map<String, Object> archivedPage = reviews.list(alice, null, null, "archived", 0, 20);
        assertEquals(1L, archivedPage.get("total"));

        Map<String, Object> decided = reviews.decide(alice, reviewId, "approve", 1, "alice", "ok");
        assertEquals("approved", decided.get("status"));
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.tasks WHERE case_id=?", Integer.class, aliceCase.id()));
    }

    private UUID insertReview(String caseId, String taskStatus, String reviewStatus) {
        return insertReview(caseId, taskStatus, reviewStatus, "{}");
    }

    private UUID insertReview(String caseId, String taskStatus, String reviewStatus, String metadataJson) {
        UUID taskId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.tasks(id, request_id, execution_id, case_id, query_text, status, current_stage, metadata_json)
                VALUES (?, ?, ?, ?, 'review-fixture', ?, 'human_review', ?::jsonb)
                """, taskId, UUID.randomUUID(), UUID.randomUUID(), caseId, taskStatus, metadataJson);
        UUID reviewId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.review_records(id, task_id, result_version, status, decision)
                VALUES (?, ?, 1, ?, 'none')
                """, reviewId, taskId, reviewStatus);
        return reviewId;
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
