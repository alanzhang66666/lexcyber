package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

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
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;

class DraftServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private DraftService drafts;
    private CaseService cases;
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
        cases = new CaseService(jdbc, new ObjectMapper().findAndRegisterModules());
        drafts = new DraftService(jdbc, cases);
        alice = insertAccount("alice_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        bob = insertAccount("bob_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8));
        aliceCase = cases.create(alice, new CaseCreate("alice-drafts", "CN", null, Map.of()));
        bobCase = cases.create(bob, new CaseCreate("bob-drafts", "CN", null, Map.of()));
    }

    @Test
    void ownerCanCreateListAndReadDraft() {
        DraftView created = drafts.create(alice, aliceCase.id(), new DraftCreate("opinion", "初稿"));
        assertTrue(created.id().startsWith("draft-"));
        assertEquals(aliceCase.id(), created.caseId());
        assertEquals("opinion", created.draftType());
        assertEquals("初稿", created.body());
        assertEquals(1, created.version());
        assertEquals(alice, created.updatedBy());

        DraftList page = drafts.list(alice, aliceCase.id());
        assertEquals(1, page.items().size());
        assertEquals(created.id(), page.items().get(0).id());
        assertEquals(created.id(), drafts.get(alice, aliceCase.id(), created.id()).id());
    }

    @Test
    void otherCaseAndOwnerAreHidden() {
        DraftView created = drafts.create(alice, aliceCase.id(), new DraftCreate("opinion", "私有"));
        ApiException hiddenOwner = assertThrows(ApiException.class,
                () -> drafts.get(bob, aliceCase.id(), created.id()));
        assertEquals(HttpStatus.NOT_FOUND, hiddenOwner.status());
        assertEquals("CASE_NOT_FOUND", hiddenOwner.code());

        ApiException hiddenDraft = assertThrows(ApiException.class,
                () -> drafts.get(alice, aliceCase.id(), "draft-missing"));
        assertEquals("DRAFT_NOT_FOUND", hiddenDraft.code());

        ApiException crossCase = assertThrows(ApiException.class,
                () -> drafts.get(alice, bobCase.id(), created.id()));
        assertEquals("CASE_NOT_FOUND", crossCase.code());

        ApiException listHidden = assertThrows(ApiException.class, () -> drafts.list(bob, aliceCase.id()));
        assertEquals("CASE_NOT_FOUND", listHidden.code());
    }

    @Test
    void replaceIncrementsVersionAndRejectsStaleWrite() {
        DraftView created = drafts.create(alice, aliceCase.id(), new DraftCreate("judgment", ""));
        DraftView updated = drafts.replace(alice, aliceCase.id(), created.id(), new DraftUpdate("二稿", 1));
        assertEquals("二稿", updated.body());
        assertEquals(2, updated.version());

        ApiException stale = assertThrows(ApiException.class,
                () -> drafts.replace(alice, aliceCase.id(), created.id(), new DraftUpdate("旧版本", 1)));
        assertEquals(HttpStatus.CONFLICT, stale.status());
        assertEquals("DRAFT_VERSION_CONFLICT", stale.code());
        assertEquals(2, drafts.get(alice, aliceCase.id(), created.id()).version());

        ApiException hidden = assertThrows(ApiException.class,
                () -> drafts.replace(bob, aliceCase.id(), created.id(), new DraftUpdate("偷改", 2)));
        assertEquals("CASE_NOT_FOUND", hidden.code());
    }

    @Test
    void replaceSupersedesPendingAndApprovedReviewsOnOldVersion() {
        DraftView created = drafts.create(alice, aliceCase.id(),
                new DraftCreate("opinion", "初稿", "tpl-1", "src-1"));
        assertEquals("tpl-1", created.templateVersion());
        assertEquals("src-1", created.sourceVersion());
        UUID pending = UUID.randomUUID();
        UUID approved = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.review_records(id, task_id, result_version, status, decision, case_id, draft_id, draft_version)
                VALUES (?, NULL, 1, 'pending', 'none', ?, ?, 1)
                """, pending, aliceCase.id(), created.id());
        jdbc.update("""
                INSERT INTO app.review_records(id, task_id, result_version, status, decision, case_id, draft_id, draft_version)
                VALUES (?, NULL, 1, 'approved', 'approve', ?, ?, 1)
                """, approved, aliceCase.id(), created.id());

        DraftView updated = drafts.replace(alice, aliceCase.id(), created.id(),
                new DraftUpdate("二稿", 1, "tpl-2", "src-2"));
        assertEquals(2, updated.version());
        assertEquals("tpl-2", updated.templateVersion());
        assertEquals("superseded", jdbc.queryForObject(
                "SELECT status FROM app.review_records WHERE id=?", String.class, pending));
        assertEquals("superseded", jdbc.queryForObject(
                "SELECT status FROM app.review_records WHERE id=?", String.class, approved));
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
