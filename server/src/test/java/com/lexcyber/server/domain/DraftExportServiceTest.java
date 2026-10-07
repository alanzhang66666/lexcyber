package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.engine.DraftExportEngineClient;
import com.lexcyber.server.storage.InMemoryObjectStorage;
import com.lexcyber.server.storage.ObjectStorage;
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

class DraftExportServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private JdbcTemplate jdbc;
    private CaseService cases;
    private DraftService drafts;
    private DraftExportEngineClient engine;
    private InMemoryObjectStorage storage;
    private DraftExportService exports;
    private UUID alice;
    private UUID bob;
    private CaseView aliceCase;
    private CaseView aliceOtherCase;
    private CaseView bobCase;

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
        ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();
        cases = new CaseService(jdbc, objectMapper, new IdempotencyService(jdbc));
        drafts = new DraftService(jdbc, cases,
                new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc)));
        engine = mock(DraftExportEngineClient.class);
        when(engine.render(any())).thenReturn("docx-bytes".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        storage = new InMemoryObjectStorage();
        exports = new DraftExportService(jdbc, cases, objectMapper, engine, storage);
        alice = insertAccount("export-alice-" + UUID.randomUUID());
        bob = insertAccount("export-bob-" + UUID.randomUUID());
        aliceCase = cases.create(alice, new CaseCreate("export-a", "CN", null, Map.of()));
        aliceOtherCase = cases.create(alice, new CaseCreate("export-a-other", "CN", null, Map.of()));
        bobCase = cases.create(bob, new CaseCreate("export-b", "CN", null, Map.of()));
    }

    @Test
    void exportsExactManualHistoryAndDoesNotMoveHead() {
        DraftView first = drafts.create(alice, aliceCase.id(), new DraftCreate("old-opinion", "旧正文"));
        DraftView second = drafts.replace(alice, aliceCase.id(), first.id(), new DraftUpdate("新正文", first.version()));
        UUID streamId = jdbc.queryForObject("SELECT artifact_stream_id FROM app.artifact_version WHERE artifact_version_id=?",
                UUID.class, first.artifactVersionId());
        jdbc.update("UPDATE app.case_drafts SET draft_type='mutable-current' WHERE id=?::uuid", first.id());
        jdbc.update("UPDATE app.artifact_stream SET scope_key=? WHERE artifact_stream_id=?",
                "legacy:" + first.id(), streamId);
        clearInvocations(engine);

        DraftExportService.ExportedDocx exported = exports.export(alice, aliceCase.id(), first.artifactVersionId());

        @SuppressWarnings("unchecked")
        org.mockito.ArgumentCaptor<Map<String, Object>> request = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(engine).render(request.capture());
        assertEquals(first.artifactVersionId().toString(), request.getValue().get("artifact_version_id"));
        assertEquals("旧正文", request.getValue().get("body"));
        assertEquals("old-opinion", request.getValue().get("doc_type"));
        assertEquals(first.artifactVersionId(), exported.artifactVersionId());
        assertEquals(second.artifactVersionId(), jdbc.queryForObject(
                "SELECT latest_version_id FROM app.artifact_stream WHERE artifact_stream_id=?",
                UUID.class, streamId));
    }

    @Test
    void exportsRenderedDraftV2UsingItsImmutableDocumentType() {
        DraftView descriptor = drafts.create(alice, aliceCase.id(), new DraftCreate("mutable-descriptor", "手工正文"));
        ArtifactPublicationService publication = new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc));
        UUID rendered = publication.publish(new ArtifactPublicationService.PublishRequest(
                aliceCase.id(), "draft", "draft:" + descriptor.id(), "draft.v2", "calculated",
                "{\"doc_type\":\"rendered-opinion\",\"body\":\"渲染正文\",\"unresolved\":[]}",
                "[]", "{}", null, List.of(), List.of(), null, null, null)).artifactVersionId();

        exports.export(alice, aliceCase.id(), rendered);

        @SuppressWarnings("unchecked")
        org.mockito.ArgumentCaptor<Map<String, Object>> request = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(engine).render(request.capture());
        assertEquals(rendered.toString(), request.getValue().get("artifact_version_id"));
        assertEquals("rendered-opinion", request.getValue().get("doc_type"));
        assertEquals("渲染正文", request.getValue().get("body"));
    }

    @Test
    void hidesUnknownCrossCaseAndOtherOwner() {
        DraftView draft = drafts.create(alice, aliceCase.id(), new DraftCreate("opinion", "正文"));
        ApiException otherOwner = assertThrows(ApiException.class,
                () -> exports.export(bob, aliceCase.id(), draft.artifactVersionId()));
        assertEquals(HttpStatus.NOT_FOUND, otherOwner.status());
        assertEquals("CASE_NOT_FOUND", otherOwner.code());
        ApiException crossCase = assertThrows(ApiException.class,
                () -> exports.export(alice, aliceOtherCase.id(), draft.artifactVersionId()));
        assertEquals(HttpStatus.NOT_FOUND, crossCase.status());
        assertEquals("ARTIFACT_NOT_FOUND", crossCase.code());
        ApiException unknown = assertThrows(ApiException.class,
                () -> exports.export(alice, aliceCase.id(), UUID.randomUUID()));
        assertEquals("ARTIFACT_NOT_FOUND", unknown.code());
    }

    @Test
    void blocksBlankBlockedUnresolvedAndNonDraftWithoutCallingEngine() {
        DraftView blank = drafts.create(alice, aliceCase.id(), new DraftCreate("blank", ""));
        assertBlocked(blank.artifactVersionId());

        ArtifactPublicationService publication = new ArtifactPublicationService(jdbc, new StalePropagationService(jdbc));
        DraftView blocked = drafts.create(alice, aliceCase.id(), new DraftCreate("blocked", "正文"));
        UUID blockedVersion = publication.publish(new ArtifactPublicationService.PublishRequest(
                aliceCase.id(), "draft", "draft:" + blocked.id(), "case.draft.v1", "blocked",
                "{\"draft_type\":\"blocked\",\"body\":\"正文\"}", "[{\"code\":\"UPSTREAM\"}]", "{}",
                null, List.of(), List.of(), null, null, null)).artifactVersionId();
        assertBlocked(blockedVersion);

        DraftView unresolved = drafts.create(alice, aliceCase.id(), new DraftCreate("unresolved", "正文"));
        UUID unresolvedVersion = publication.publish(new ArtifactPublicationService.PublishRequest(
                aliceCase.id(), "draft", "draft:" + unresolved.id(), "draft.v2", "calculated",
                "{\"doc_type\":\"unresolved\",\"body\":\"正文\",\"unresolved\":[{\"path\":\"body\"}]}",
                "[]", "{}", null, List.of(), List.of(), null, null, null)).artifactVersionId();
        assertBlocked(unresolvedVersion);

        UUID moduleVersion = publication.publish(new ArtifactPublicationService.PublishRequest(
                aliceCase.id(), "compliance", "module:compliance", "compliance.v2", "calculated",
                "{\"body\":\"模块正文\"}", "[]", "{}", null, List.of(), List.of(), null, null, null)).artifactVersionId();
        assertBlocked(moduleVersion);
        org.mockito.Mockito.verifyNoInteractions(engine);
    }

    @Test
    void reportsStorageReadbackMismatch() {
        DraftView draft = drafts.create(alice, aliceCase.id(), new DraftCreate("opinion", "正文"));
        ObjectStorage mismatch = new ObjectStorage() {
            @Override public void put(String key, byte[] data, String contentType) {}
            @Override public byte[] get(String key) { return "different".getBytes(java.nio.charset.StandardCharsets.UTF_8); }
            @Override public void delete(String key) {}
        };
        DraftExportService service = new DraftExportService(jdbc, cases, new ObjectMapper().findAndRegisterModules(), engine, mismatch);
        ApiException error = assertThrows(ApiException.class,
                () -> service.export(alice, aliceCase.id(), draft.artifactVersionId()));
        assertEquals("DRAFT_EXPORT_STORAGE_FAILED", error.code());
    }

    private void assertBlocked(UUID artifactVersionId) {
        ApiException error = assertThrows(ApiException.class,
                () -> exports.export(alice, aliceCase.id(), artifactVersionId));
        assertEquals(HttpStatus.CONFLICT, error.status());
        assertEquals("DRAFT_EXPORT_BLOCKED", error.code());
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
