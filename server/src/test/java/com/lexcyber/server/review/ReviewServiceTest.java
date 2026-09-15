package com.lexcyber.server.review;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.CaseCreate;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
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
        reviews = new ReviewService(jdbc);
        CaseService cases = new CaseService(jdbc, new ObjectMapper().findAndRegisterModules());
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

        Map<String, Object> owned = reviews.get(alice, aliceReview);
        assertEquals(aliceCase.id(), owned.get("caseId"));
        assertEquals(1, owned.get("resultVersion"));

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

    private UUID insertReview(String caseId, String taskStatus, String reviewStatus) {
        UUID taskId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.tasks(id, request_id, execution_id, case_id, query_text, status, current_stage, metadata_json)
                VALUES (?, ?, ?, ?, 'review-fixture', ?, 'human_review', '{}'::jsonb)
                """, taskId, UUID.randomUUID(), UUID.randomUUID(), caseId, taskStatus);
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
