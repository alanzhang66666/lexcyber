package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.storage.InMemoryObjectStorage;
import java.time.LocalDate;
import java.util.Map;
import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers(disabledWithoutDocker = true)
class CaseDocumentServiceTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("lexcyber")
            .withUsername("lex_app")
            .withPassword("lex_app");

    private CaseService cases;
    private DocumentService documents;
    private FactService facts;
    private JdbcTemplate jdbc;
    private InMemoryObjectStorage storage;
    private UUID alice;
    private UUID bob;

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
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        cases = new CaseService(jdbc, mapper);
        TaskService tasks = new TaskService(jdbc, mapper);
        storage = new InMemoryObjectStorage();
        documents = new DocumentService(jdbc, cases, tasks, storage);
        facts = new FactService(jdbc, mapper, cases);
        alice = insertAccount("alice");
        bob = insertAccount("bob");
    }

    @Test
    void createListGetAndUploadPersistAcrossReload() {
        CaseView created = cases.create(alice, new CaseCreate("测试案例 001", "CN", LocalDate.parse("2026-09-06"),
                Map.of("datasetCaseNo", "001", "isDevelopmentSample", true)));
        assertTrue(created.id().startsWith("case-"));
        assertEquals("CN", created.jurisdiction());
        assertEquals(LocalDate.parse("2026-09-06"), created.asOfDate());

        PageResponse<CaseView> page = cases.list(alice, 0, 20);
        assertEquals(1, page.total());
        assertEquals(created.id(), page.items().get(0).id());
        assertEquals(created.id(), cases.requireOwned(alice, created.id()).id());

        byte[] inputBytes = "input-body".getBytes();
        DocumentView input = documents.upload(alice, created.id(), "案情材料.docx", DocumentPolicies.DOCX,
                inputBytes, "input", "upload-demo-001");
        assertEquals("queued", input.parseStatus());
        assertNotNull(input.parseTaskId());
        assertTrue(storage.contains(DocumentPolicies.storageKey(created.id(), input.id(), DocumentPolicies.sha256Hex(inputBytes))));

        DocumentView reloaded = documents.requireOwned(alice, input.id());
        assertEquals(input.id(), reloaded.id());
        assertEquals(input.parseTaskId(), reloaded.parseTaskId());
        assertEquals("input", reloaded.role());

        DocumentView annotation = documents.upload(alice, created.id(), "批注.docx", DocumentPolicies.DOCX,
                "annotation-body".getBytes(), "annotation", "upload-demo-002");
        assertEquals("annotation", annotation.role());
        assertNotEquals(input.id(), annotation.id());
        PageResponse<DocumentView> inputs = documents.list(alice, created.id(), "input", 0, 20);
        PageResponse<DocumentView> notes = documents.list(alice, created.id(), "annotation", 0, 20);
        assertEquals(1, inputs.total());
        assertEquals(1, notes.total());
        assertEquals("input", inputs.items().get(0).role());
        assertEquals("annotation", notes.items().get(0).role());

        Map<String, Object> task = jdbc.queryForMap("SELECT query_text, metadata_json FROM app.tasks WHERE id = ?", input.parseTaskId());
        assertTrue(String.valueOf(task.get("query_text")).contains("解析"));
        assertTrue(String.valueOf(task.get("metadata_json")).contains("document.parse"));
        Long outbox = jdbc.queryForObject("SELECT COUNT(*) FROM app.task_dispatch_outbox WHERE task_id = ?", Long.class, input.parseTaskId());
        assertEquals(1L, outbox);
    }

    @Test
    void idempotentUploadReturnsOriginalAndConflictOnDifferentContent() {
        CaseView created = cases.create(alice, new CaseCreate("idem", "CN", null, Map.of()));
        byte[] first = "same-bytes".getBytes();
        DocumentView original = documents.upload(alice, created.id(), "a.docx", DocumentPolicies.DOCX, first, "input", "key-1");
        DocumentView replay = documents.upload(alice, created.id(), "a.docx", DocumentPolicies.DOCX, first, "input", "key-1");
        assertEquals(original.id(), replay.id());
        assertEquals(original.parseTaskId(), replay.parseTaskId());

        ApiException conflict = assertThrows(ApiException.class, () -> documents.upload(
                alice, created.id(), "b.docx", DocumentPolicies.DOCX, "other-bytes".getBytes(), "input", "key-1"));
        assertEquals(HttpStatus.CONFLICT, conflict.status());
        assertEquals("IDEMPOTENCY_CONFLICT", conflict.code());
    }

    @Test
    void crossUserAccessIs404() {
        CaseView created = cases.create(alice, new CaseCreate("secret", "CN", null, Map.of()));
        DocumentView document = documents.upload(alice, created.id(), "a.pdf", "application/pdf", "pdf".getBytes(), "input", null);
        ApiException hiddenCase = assertThrows(ApiException.class, () -> cases.requireOwned(bob, created.id()));
        assertEquals("CASE_NOT_FOUND", hiddenCase.code());
        ApiException hiddenDoc = assertThrows(ApiException.class, () -> documents.requireOwned(bob, document.id()));
        assertEquals("DOCUMENT_NOT_FOUND", hiddenDoc.code());
        ApiException hiddenParse = assertThrows(ApiException.class, () -> documents.requireOwnedForParse(bob, document.id()));
        assertEquals("DOCUMENT_NOT_FOUND", hiddenParse.code());
        DocumentService.StoredDocument owned = documents.requireOwnedForParse(alice, document.id());
        assertEquals(document.id(), owned.id());
        assertEquals(created.id(), owned.caseId());
        assertNotNull(owned.storageKey());
        assertEquals(0, cases.list(bob, 0, 20).total());
    }

    @Test
    void factsDraftCanBeReplacedThenLocked() {
        CaseView created = cases.create(alice, new CaseCreate("facts", "CN", null, Map.of()));
        FactView empty = facts.get(alice, created.id());
        assertEquals("draft", empty.status());
        assertEquals(0, empty.items().size());

        FactView written = facts.replace(alice, created.id(),
                new FactUpdate(java.util.List.of(new FactItem(null, "amount", "100", "paragraph:1", "doc-1"))));
        assertEquals("draft", written.status());
        assertEquals(1, written.items().size());
        assertEquals("amount", written.items().get(0).key());

        FactView confirmed = facts.confirm(alice, created.id());
        assertEquals("confirmed", confirmed.status());
        ApiException locked = assertThrows(ApiException.class, () -> facts.replace(alice, created.id(),
                new FactUpdate(java.util.List.of(new FactItem(null, "amount", "200", null, null)))));
        assertEquals("FACTS_CONFIRMED", locked.code());
        ApiException again = assertThrows(ApiException.class, () -> facts.confirm(alice, created.id()));
        assertEquals("FACTS_CONFIRMED", again.code());
        ApiException hidden = assertThrows(ApiException.class, () -> facts.get(bob, created.id()));
        assertEquals("CASE_NOT_FOUND", hidden.code());
    }

    @Test
    void unknownAndSentencingTaskTypesAreRejected() {
        TaskService gated = new TaskService(jdbc, new ObjectMapper().findAndRegisterModules(), false);
        ApiException unknown = assertThrows(ApiException.class,
                () -> gated.create(new TaskCreate("q", null, null, Map.of("taskType", "nope"))));
        assertEquals("INVALID_TASK_TYPE", unknown.code());
        ApiException sentencing = assertThrows(ApiException.class,
                () -> gated.create(new TaskCreate("q", null, null, Map.of("taskType", "sentencing.calculate"))));
        assertEquals(HttpStatus.NOT_IMPLEMENTED, sentencing.status());
        assertEquals("SENTENCING_UNAVAILABLE", sentencing.code());
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
        dataSource.setUrl(POSTGRES.getJdbcUrl());
        dataSource.setUsername(POSTGRES.getUsername());
        dataSource.setPassword(POSTGRES.getPassword());
        return dataSource;
    }
}
