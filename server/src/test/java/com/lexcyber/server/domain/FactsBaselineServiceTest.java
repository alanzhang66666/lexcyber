package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
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

/**
 * P2 事实闭环验收（补充计划 §P2）：
 * 六类实体均进快照；CAS expected-head 双确认一成一 409；clone 回写工作副本；
 * diff 报告增删改；确认后编辑不污染旧快照；/v1 confirmed 后 PUT 仍 409。
 */
class FactsBaselineServiceTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private JdbcTemplate jdbc;
    private FactsBaselineService baseline;
    private FactService facts;
    private CaseService cases;
    private ObjectMapper mapper;
    private UUID alice;
    private CaseView aliceCase;

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
        mapper = new ObjectMapper().findAndRegisterModules();
        baseline = new FactsBaselineService(jdbc, new StalePropagationService(jdbc));
        cases = new CaseService(jdbc, mapper, new IdempotencyService(jdbc));
        facts = new FactService(jdbc, cases, baseline);
        alice = insertAccount("alice_" + shortId());
        aliceCase = cases.create(alice, new CaseCreate("alice-facts-" + shortId(), "CN", null, Map.of()));
    }

    @Test
    void snapshotCoversAllSixEntityKinds() {
        seedAllEntities(aliceCase.id());
        UUID versionId = baseline.createDraftVersion(aliceCase.id(), alice);

        Map<String, Object> detail = baseline.versionDetail(aliceCase.id(), versionId);
        @SuppressWarnings("unchecked")
        Map<String, Object> payload = (Map<String, Object>) detail.get("payload");
        @SuppressWarnings("unchecked")
        List<Object> items = (List<Object>) payload.get("items");
        @SuppressWarnings("unchecked")
        Map<String, Object> entities = (Map<String, Object>) payload.get("entities");
        assertEquals(1, items.size());
        for (String key : List.of("actors", "events", "evidence", "amounts", "jurisdictionConnections")) {
            @SuppressWarnings("unchecked")
            List<Object> section = (List<Object>) entities.get(key);
            assertNotNull(section, "missing section " + key);
            assertEquals(1, section.size(), "section " + key + " should have one row");
        }

        // facts_version_item 每类各一条
        List<Map<String, Object>> index = jdbc.queryForList(
                "SELECT entity_kind, COUNT(*) AS n FROM app.facts_version_item" +
                        " WHERE facts_version_id = ? GROUP BY entity_kind", versionId);
        assertEquals(6, index.size());
        for (Map<String, Object> row : index) {
            assertEquals(1L, ((Number) row.get("n")).longValue(), String.valueOf(row.get("entity_kind")));
        }
    }

    @Test
    void confirmEnforcesExpectedHeadCas() {
        UUID v1 = baseline.createDraftVersion(aliceCase.id(), alice);
        baseline.confirm(aliceCase.id(), v1, null, alice);
        assertEquals(v1, baseline.confirmedVersionId(aliceCase.id()).orElseThrow());

        UUID v2 = baseline.createDraftVersion(aliceCase.id(), alice);
        // 过期 expected（仍以为无 head）→ 409
        ApiException stale = assertThrows(ApiException.class,
                () -> baseline.confirm(aliceCase.id(), v2, null, alice));
        assertEquals(HttpStatus.CONFLICT, stale.status());
        assertEquals("FACTS_HEAD_CONFLICT", stale.code());
        // head 未被覆盖
        assertEquals(v1, baseline.confirmedVersionId(aliceCase.id()).orElseThrow());
        // v2 仍可确认（CAS 失败不消耗版本）
        baseline.confirm(aliceCase.id(), v2, v1, alice);
        assertEquals(v2, baseline.confirmedVersionId(aliceCase.id()).orElseThrow());
    }

    @Test
    void confirmingSameVersionTwiceIsRejected() {
        UUID v1 = baseline.createDraftVersion(aliceCase.id(), alice);
        baseline.confirm(aliceCase.id(), v1, null, alice);
        ApiException again = assertThrows(ApiException.class,
                () -> baseline.confirm(aliceCase.id(), v1, v1, alice));
        assertEquals("FACTS_VERSION_NOT_CONFIRMABLE", again.code());
    }

    @Test
    void cloneRestoresWorkingCopyFromOldVersion() {
        seedAllEntities(aliceCase.id());
        UUID v1 = baseline.createDraftVersion(aliceCase.id(), alice);

        // 改动工作副本
        baseline.replaceEntities(aliceCase.id(), "facts",
                List.of(Map.of("id", "f-new", "key", "k2", "value", "v2")));
        baseline.replaceEntities(aliceCase.id(), "amounts", List.of());
        assertEquals(0, count("case_amount", aliceCase.id()));
        assertEquals(1, count("case_fact", aliceCase.id()));

        baseline.cloneIntoWorkingCopy(aliceCase.id(), v1);
        assertEquals(1, count("case_fact", aliceCase.id()));
        assertEquals(1, count("case_amount", aliceCase.id()));
        assertEquals(1, count("case_actor", aliceCase.id()));
        String key = jdbc.queryForObject(
                "SELECT fact_key FROM app.case_fact WHERE case_id = ?::uuid", String.class, aliceCase.id());
        assertEquals("k1", key);
    }

    @Test
    void diffReportsAddedRemovedChanged() {
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f1", "key", "k1", "value", "v1"),
                Map.of("id", "f2", "key", "k2", "value", "v2")));
        UUID v1 = baseline.createDraftVersion(aliceCase.id(), alice);

        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f1", "key", "k1", "value", "v1-changed"),
                Map.of("id", "f3", "key", "k3", "value", "v3")));
        UUID v2 = baseline.createDraftVersion(aliceCase.id(), alice);

        Map<String, Object> diff = baseline.diffVersions(aliceCase.id(), v1, v2);
        @SuppressWarnings("unchecked")
        Map<String, Object> sections = (Map<String, Object>) diff.get("sections");
        @SuppressWarnings("unchecked")
        Map<String, Object> items = (Map<String, Object>) sections.get("items");
        @SuppressWarnings("unchecked")
        List<Object> added = (List<Object>) items.get("added");
        @SuppressWarnings("unchecked")
        List<Object> removed = (List<Object>) items.get("removed");
        @SuppressWarnings("unchecked")
        List<Object> changed = (List<Object>) items.get("changed");
        assertEquals(1, added.size());
        assertEquals(1, removed.size());
        assertEquals(1, changed.size());
        @SuppressWarnings("unchecked")
        Map<String, Object> change = (Map<String, Object>) changed.get(0);
        assertEquals("f1", change.get("id"));
    }

    @Test
    void editingAfterConfirmOnlyAffectsNextVersion() {
        baseline.replaceEntities(aliceCase.id(), "facts",
                List.of(Map.of("id", "f1", "key", "k1", "value", "original")));
        UUID v1 = baseline.createDraftVersion(aliceCase.id(), alice);
        baseline.confirm(aliceCase.id(), v1, null, alice);

        // /v2 编辑路径不受 confirmed 限制
        baseline.replaceEntities(aliceCase.id(), "facts",
                List.of(Map.of("id", "f1", "key", "k1", "value", "edited")));
        UUID v2 = baseline.createDraftVersion(aliceCase.id(), alice);
        baseline.confirm(aliceCase.id(), v2, v1, alice);

        // 旧快照内容不被污染
        Map<String, Object> v1Detail = baseline.versionDetail(aliceCase.id(), v1);
        @SuppressWarnings("unchecked")
        List<Object> v1Items = (List<Object>)
                ((Map<String, Object>) v1Detail.get("payload")).get("items");
        @SuppressWarnings("unchecked")
        Map<String, Object> first = (Map<String, Object>) v1Items.get(0);
        assertEquals("original", first.get("value"));
        assertEquals("superseded", v1Detail.get("status"));
    }

    @Test
    void v1ConfirmedRejectsFurtherWrites() {
        facts.replace(alice, aliceCase.id(),
                new FactUpdate(List.of(new FactItem(null, "k", "v", null, null))));
        facts.confirm(alice, aliceCase.id());
        ApiException locked = assertThrows(ApiException.class, () ->
                facts.replace(alice, aliceCase.id(),
                        new FactUpdate(List.of(new FactItem(null, "k", "v2", null, null)))));
        assertEquals("FACTS_CONFIRMED", locked.code());
    }

    @Test
    void amountKindClosedSetEnforced() {
        ApiException bad = assertThrows(ApiException.class, () ->
                baseline.replaceEntities(aliceCase.id(), "amounts",
                        List.of(Map.of("id", "a1", "kind", "revenue_maybe", "value", 100))));
        assertEquals(HttpStatus.BAD_REQUEST, bad.status());
        // 合法 kind 通过
        baseline.replaceEntities(aliceCase.id(), "amounts",
                List.of(Map.of("id", "a1", "kind", "illegal_gain", "value", 100, "label", "x")));
        assertEquals(1, count("case_amount", aliceCase.id()));
    }

    @Test
    void amountComponentsResolveWithinReplacementRegardlessOfOrder() {
        baseline.replaceEntities(aliceCase.id(), "amounts", List.of(
                Map.of("id", "child", "kind", "illegal_gain", "value", 10, "componentOf", "parent"),
                Map.of("id", "parent", "kind", "crime_amount", "value", 20)));

        UUID parentId = jdbc.queryForObject(
                "SELECT amount_id FROM app.case_amount WHERE case_id = ?::uuid AND external_id = 'parent'",
                UUID.class, aliceCase.id());
        UUID childParent = jdbc.queryForObject(
                "SELECT component_of FROM app.case_amount WHERE case_id = ?::uuid AND external_id = 'child'",
                UUID.class, aliceCase.id());
        assertEquals(parentId, childParent);
    }

    @Test
    void amountComponentsAcceptSnapshotEntityIdAliases() {
        UUID oldParentId = UUID.randomUUID();
        UUID oldChildId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.case_amount(amount_id, case_id, external_id, kind, value)
                VALUES (?, ?::uuid, 'old-parent', 'crime_amount', 20),
                       (?, ?::uuid, 'old-child', 'illegal_gain', 10)
                """, oldParentId, aliceCase.id(), oldChildId, aliceCase.id());

        baseline.replaceEntities(aliceCase.id(), "amounts", List.of(
                Map.of("id", "child", "entityId", oldChildId.toString(),
                        "kind", "illegal_gain", "componentOf", oldParentId.toString()),
                Map.of("id", "parent", "entityId", oldParentId.toString(),
                        "kind", "crime_amount", "value", 20)));
        UUID parentId = jdbc.queryForObject(
                "SELECT amount_id FROM app.case_amount WHERE case_id = ?::uuid AND external_id = 'parent'",
                UUID.class, aliceCase.id());
        assertEquals(parentId, jdbc.queryForObject(
                "SELECT component_of FROM app.case_amount WHERE case_id = ?::uuid AND external_id = 'child'",
                UUID.class, aliceCase.id()));
    }

    @Test
    @SuppressWarnings("unchecked")
    void immutableAmountSnapshotCanBeReplacedTwiceWithoutLosingComponents() {
        baseline.replaceEntities(aliceCase.id(), "amounts", List.of(
                Map.of("id", "child", "kind", "illegal_gain", "value", 10, "componentOf", "parent"),
                Map.of("id", "parent", "kind", "illegal_gain", "value", 20)));
        UUID versionId = baseline.createDraftVersion(aliceCase.id(), alice);
        Map<String, Object> payload = (Map<String, Object>) baseline.versionDetail(
                aliceCase.id(), versionId).get("payload");
        Map<String, Object> entities = (Map<String, Object>) payload.get("entities");
        List<Map<String, Object>> originalRows = (List<Map<String, Object>>) entities.get("amounts");

        for (int attempt = 0; attempt < 2; attempt++) {
            baseline.replaceEntities(aliceCase.id(), "amounts", originalRows);
            assertEquals(2, count("case_amount", aliceCase.id()));
            UUID parentId = jdbc.queryForObject(
                    "SELECT amount_id FROM app.case_amount WHERE case_id = ?::uuid AND external_id = 'parent'",
                    UUID.class, aliceCase.id());
            assertEquals(parentId, jdbc.queryForObject(
                    "SELECT component_of FROM app.case_amount WHERE case_id = ?::uuid AND external_id = 'child'",
                    UUID.class, aliceCase.id()));
        }
        assertEquals(payload, baseline.versionDetail(aliceCase.id(), versionId).get("payload"));
    }

    @Test
    void invalidAmountComponentGraphsAreRejectedBeforeReplacement() {
        baseline.replaceEntities(aliceCase.id(), "amounts",
                List.of(Map.of("id", "original", "kind", "illegal_gain", "value", 7)));

        List<List<Map<String, Object>>> invalid = List.of(
                List.of(Map.of("id", "a", "kind", "illegal_gain", "componentOf", "missing")),
                List.of(Map.of("kind", "illegal_gain", "componentOf", "a")),
                List.of(Map.of("kind", "illegal_gain", "componentOf", "parent"),
                        Map.of("id", "parent", "kind", "illegal_gain", "value", 10)),
                List.of(Map.of("id", "a", "kind", "illegal_gain", "componentOf", "a")),
                List.of(
                        Map.of("id", "a", "kind", "illegal_gain", "componentOf", "b"),
                        Map.of("id", "b", "kind", "illegal_gain", "componentOf", "a")),
                List.of(
                        Map.of("id", "a", "kind", "illegal_gain"),
                        Map.of("id", "a", "kind", "crime_amount")));
        for (List<Map<String, Object>> items : invalid) {
            ApiException error = assertThrows(ApiException.class,
                    () -> baseline.replaceEntities(aliceCase.id(), "amounts", items));
            assertEquals(HttpStatus.BAD_REQUEST, error.status());
            assertEquals("INVALID_REQUEST", error.code());
            assertEquals(1, count("case_amount", aliceCase.id()));
        }
    }

    @Test
    void amountComponentUuidMustBelongToReplacementCase() {
        String otherCase = cases.create(alice,
                new CaseCreate("alice-other-" + shortId(), "CN", null, Map.of())).id();
        UUID otherAmount = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.case_amount(amount_id, case_id, external_id, kind, value)
                VALUES (?, ?::uuid, 'other', 'illegal_gain', 9)
                """, otherAmount, otherCase);
        baseline.replaceEntities(aliceCase.id(), "amounts",
                List.of(Map.of("id", "original", "kind", "illegal_gain", "value", 7)));

        ApiException error = assertThrows(ApiException.class, () -> baseline.replaceEntities(aliceCase.id(), "amounts",
                List.of(Map.of("id", "child", "kind", "illegal_gain", "componentOf", otherAmount.toString()))));
        assertEquals(HttpStatus.BAD_REQUEST, error.status());
        assertEquals(1, count("case_amount", aliceCase.id()));
    }

    @Test
    void evidenceReplacementKeepsCanonicalIdAndRejectsReferencedRemoval() {
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "e-1", "type", "document", "label", "流水")));
        UUID evidenceId = jdbc.queryForObject(
                "SELECT evidence_id FROM app.case_evidence WHERE case_id = ?::uuid AND external_id = 'e-1'",
                UUID.class, aliceCase.id());
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f-1", "key", "amount", "value", "20", "evidenceIds", List.of("e-1"))));

        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "e-1", "type", "document", "label", "流水（修订）")));
        assertEquals(evidenceId, jdbc.queryForObject(
                "SELECT evidence_id FROM app.case_evidence WHERE case_id = ?::uuid AND external_id = 'e-1'",
                UUID.class, aliceCase.id()));
        assertEquals(evidenceId.toString(), jdbc.queryForObject(
                "SELECT evidence_ids ->> 0 FROM app.case_fact WHERE case_id = ?::uuid",
                String.class, aliceCase.id()));

        ApiException error = assertThrows(ApiException.class,
                () -> baseline.replaceEntities(aliceCase.id(), "evidence", List.of()));
        assertEquals(HttpStatus.CONFLICT, error.status());
        assertEquals("ENTITY_REFERENCED", error.code());
        assertEquals(1, count("case_evidence", aliceCase.id()));
    }

    @Test
    void explicitCanonicalIdentityDoesNotDiscardNewExternalAlias() {
        baseline.replaceEntities(aliceCase.id(), "evidence", List.of(
                Map.of("id", "old-alias", "type", "document")));
        UUID canonical = jdbc.queryForObject("SELECT evidence_id FROM app.case_evidence WHERE case_id = ?::uuid",
                UUID.class, aliceCase.id());
        baseline.replaceEntities(aliceCase.id(), "evidence", List.of(
                Map.of("entityId", canonical.toString(), "id", "new-alias", "type", "document")));
        assertEquals(canonical, jdbc.queryForObject("SELECT evidence_id FROM app.case_evidence WHERE case_id = ?::uuid",
                UUID.class, aliceCase.id()));
        assertEquals("new-alias", jdbc.queryForObject("SELECT external_id FROM app.case_evidence WHERE case_id = ?::uuid",
                String.class, aliceCase.id()));
    }

    @Test
    void uuidShapedExternalIdPutKeepsItsStableEvidenceIdentity() {
        String externalId = UUID.randomUUID().toString();
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", externalId, "type", "document", "label", "原始")));
        UUID evidenceId = jdbc.queryForObject(
                "SELECT evidence_id FROM app.case_evidence WHERE case_id = ?::uuid AND external_id = ?",
                UUID.class, aliceCase.id(), externalId);
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", externalId, "type", "document", "label", "修订")));
        assertEquals(evidenceId, jdbc.queryForObject(
                "SELECT evidence_id FROM app.case_evidence WHERE case_id = ?::uuid AND external_id = ?",
                UUID.class, aliceCase.id(), externalId));
    }

    @Test
    void explicitCrossCaseEntityIdIsRejectedBeforeEvidenceReplacement() {
        String otherCase = cases.create(alice,
                new CaseCreate("alice-other-evidence-" + shortId(), "CN", null, Map.of())).id();
        UUID foreignId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.case_evidence(evidence_id, case_id, external_id, evidence_type, label)
                VALUES (?, ?::uuid, 'foreign-evidence', 'document', '跨案')
                """, foreignId, otherCase);
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "local", "type", "document", "label", "本案")));

        ApiException error = assertThrows(ApiException.class,
                () -> baseline.replaceEntities(aliceCase.id(), "evidence",
                        List.of(Map.of("entityId", foreignId.toString(), "id", "foreign-evidence"))));
        assertEquals(HttpStatus.BAD_REQUEST, error.status());
        assertEquals("INVALID_REQUEST", error.code());
        assertEquals(1, count("case_evidence", aliceCase.id()));
    }

    @Test
    void duplicateEvidenceAliasesAreRejectedBeforeChangingWorkingCopy() {
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "e-1", "type", "document", "label", "原始")));
        ApiException error = assertThrows(ApiException.class,
                () -> baseline.replaceEntities(aliceCase.id(), "evidence", List.of(
                        Map.of("id", "e-1", "type", "document", "label", "一"),
                        Map.of("id", "e-1", "type", "document", "label", "二"))));
        assertEquals(HttpStatus.BAD_REQUEST, error.status());
        assertEquals("INVALID_REQUEST", error.code());
        assertEquals(1, count("case_evidence", aliceCase.id()));
        assertEquals("原始", jdbc.queryForObject(
                "SELECT label FROM app.case_evidence WHERE case_id = ?::uuid", String.class, aliceCase.id()));
    }

    @Test
    void unreferencedActorAndEvidenceCanBeRemoved() {
        baseline.replaceEntities(aliceCase.id(), "actors",
                List.of(Map.of("id", "actor-free", "name", "未引用")));
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "e-free", "type", "document", "label", "未引用")));
        baseline.replaceEntities(aliceCase.id(), "actors", List.of());
        baseline.replaceEntities(aliceCase.id(), "evidence", List.of());
        assertEquals(0, count("case_actor", aliceCase.id()));
        assertEquals(0, count("case_evidence", aliceCase.id()));
    }

    @Test
    void actorReplacementKeepsFactAndEventForeignKeys() {
        baseline.replaceEntities(aliceCase.id(), "actors",
                List.of(Map.of("id", "actor-1", "type", "natural_person", "name", "张某")));
        UUID actorId = jdbc.queryForObject(
                "SELECT actor_id FROM app.case_actor WHERE case_id = ?::uuid AND external_id = 'actor-1'",
                UUID.class, aliceCase.id());
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f-1", "key", "actor", "value", "actor-1", "actorId", "actor-1")));
        baseline.replaceEntities(aliceCase.id(), "events", List.of(
                Map.of("id", "event-1", "actorId", "actor-1", "date", "2026-01-01")));

        baseline.replaceEntities(aliceCase.id(), "actors",
                List.of(Map.of("id", "actor-1", "type", "natural_person", "name", "张某（修订）")));
        assertEquals(actorId, jdbc.queryForObject(
                "SELECT actor_id FROM app.case_actor WHERE case_id = ?::uuid AND external_id = 'actor-1'",
                UUID.class, aliceCase.id()));
        assertEquals(actorId, jdbc.queryForObject(
                "SELECT actor_id FROM app.case_fact WHERE case_id = ?::uuid", UUID.class, aliceCase.id()));
        assertEquals(actorId, jdbc.queryForObject(
                "SELECT actor_id FROM app.case_event WHERE case_id = ?::uuid", UUID.class, aliceCase.id()));
    }

    @Test
    void unresolvedEvidenceReferenceCannotBeDraftedAndLeavesWorkingCopyUntouched() {
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f-1", "key", "amount", "value", "20", "evidenceIds", List.of("missing"))));
        ApiException error = assertThrows(ApiException.class,
                () -> baseline.createDraftVersion(aliceCase.id(), alice));
        assertEquals(HttpStatus.CONFLICT, error.status());
        assertEquals("FACTS_REFERENCE_INVALID", error.code());
        assertEquals(1, count("case_fact", aliceCase.id()));
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.facts_version WHERE case_id = ?::uuid", Integer.class, aliceCase.id()));
    }

    @Test
    void cloneUsesFrozenEvidenceAliasesAfterWorkingCopyRowsWereRemoved() {
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "e-1", "type", "document", "label", "流水")));
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f-1", "key", "amount", "value", "20", "evidenceIds", List.of("e-1"))));
        UUID versionId = baseline.createDraftVersion(aliceCase.id(), alice);

        baseline.replaceEntities(aliceCase.id(), "facts", List.of());
        baseline.replaceEntities(aliceCase.id(), "evidence", List.of());
        assertEquals(0, count("case_evidence", aliceCase.id()));

        baseline.cloneIntoWorkingCopy(aliceCase.id(), versionId);
        assertEquals(1, count("case_evidence", aliceCase.id()));
        assertEquals(1, count("case_fact", aliceCase.id()));
        String restoredEvidenceId = jdbc.queryForObject(
                "SELECT evidence_ids ->> 0 FROM app.case_fact WHERE case_id = ?::uuid",
                String.class, aliceCase.id());
        assertEquals(jdbc.queryForObject(
                "SELECT evidence_id::text FROM app.case_evidence WHERE case_id = ?::uuid",
                String.class, aliceCase.id()), restoredEvidenceId);
    }

    @Test
    void damagedFrozenPayloadCannotConfirmOrCloneOverExistingHeadAndWorkingCopy() {
        baseline.replaceEntities(aliceCase.id(), "facts",
                List.of(Map.of("id", "f-original", "key", "k", "value", "original")));
        UUID versionId = baseline.createDraftVersion(aliceCase.id(), alice);
        String damaged = """
                {"items":[{"id":"f-original","key":"k","value":"bad",
                "evidenceIds":["e-existing"]}],
                "entities":{"actors":[],"events":[],"evidence":[],"amounts":[],
                "jurisdictionConnections":[]}}
                """.replace("\n", "").replace(" ", "");
        jdbc.update("UPDATE app.facts_version SET payload = ?::jsonb WHERE facts_version_id = ?",
                damaged, versionId);

        ApiException confirmError = assertThrows(ApiException.class,
                () -> baseline.confirm(aliceCase.id(), versionId, null, alice));
        assertEquals("FACTS_REFERENCE_INVALID", confirmError.code());
        assertTrue(baseline.confirmedVersionId(aliceCase.id()).isEmpty());

        ApiException cloneError = assertThrows(ApiException.class,
                () -> baseline.cloneIntoWorkingCopy(aliceCase.id(), versionId));
        assertEquals("FACTS_REFERENCE_INVALID", cloneError.code());
        assertEquals("original", jdbc.queryForObject(
                "SELECT fact_value FROM app.case_fact WHERE case_id = ?::uuid AND external_id = 'f-original'",
                String.class, aliceCase.id()));
    }

    @Test
    void frozenMissingEvidenceCannotBeSatisfiedByCurrentWorkingCopyAlias() {
        baseline.replaceEntities(aliceCase.id(), "evidence",
                List.of(Map.of("id", "e-existing", "type", "document", "label", "当前")));
        baseline.replaceEntities(aliceCase.id(), "facts", List.of());
        UUID versionId = baseline.createDraftVersion(aliceCase.id(), alice);
        String damaged = """
                {"items":[{"id":"f-1","key":"k","value":"v",
                "evidenceIds":["e-existing"]}],
                "entities":{"actors":[],"events":[],"evidence":[],"amounts":[],
                "jurisdictionConnections":[]}}
                """.replace("\n", "").replace(" ", "");
        jdbc.update("UPDATE app.facts_version SET payload = ?::jsonb WHERE facts_version_id = ?",
                damaged, versionId);
        ApiException error = assertThrows(ApiException.class,
                () -> baseline.confirm(aliceCase.id(), versionId, null, alice));
        assertEquals("FACTS_REFERENCE_INVALID", error.code());
        assertTrue(baseline.confirmedVersionId(aliceCase.id()).isEmpty());
    }

    @Test
    void foreignActorReferenceCannotBeSolidifiedIntoDraft() {
        String otherCase = cases.create(alice,
                new CaseCreate("alice-other-actor-" + shortId(), "CN", null, Map.of())).id();
        UUID foreignActor = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.case_actor(actor_id, case_id, external_id, actor_type, name)
                VALUES (?, ?::uuid, 'foreign-actor', 'natural_person', '外案')
                """, foreignActor, otherCase);
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f-foreign", "key", "actor", "value", "x",
                        "actorId", foreignActor.toString())));
        ApiException error = assertThrows(ApiException.class,
                () -> baseline.createDraftVersion(aliceCase.id(), alice));
        assertEquals("FACTS_REFERENCE_INVALID", error.code());
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.facts_version WHERE case_id = ?::uuid", Integer.class, aliceCase.id()));
    }

    @Test
    void frozenActorExternalAliasIsCanonicalizedDuringClone() {
        baseline.replaceEntities(aliceCase.id(), "actors",
                List.of(Map.of("id", "actor-alias", "type", "natural_person", "name", "张某")));
        UUID actorId = jdbc.queryForObject(
                "SELECT actor_id FROM app.case_actor WHERE case_id = ?::uuid AND external_id = 'actor-alias'",
                UUID.class, aliceCase.id());
        baseline.replaceEntities(aliceCase.id(), "events", List.of(
                Map.of("id", "event-1", "actorId", "actor-alias", "date", "2026-01-01")));
        UUID versionId = baseline.createDraftVersion(aliceCase.id(), alice);
        jdbc.update("""
                UPDATE app.facts_version
                SET payload = jsonb_set(payload, '{entities,events,0,actorId}', '"actor-alias"'::jsonb)
                WHERE facts_version_id = ?
                """, versionId);

        baseline.cloneIntoWorkingCopy(aliceCase.id(), versionId);
        assertEquals(actorId, jdbc.queryForObject(
                "SELECT actor_id FROM app.case_event WHERE case_id = ?::uuid", UUID.class, aliceCase.id()));
    }

    @Test
    void unconfirmedItemsKeepTheirVerificationStatusInSnapshot() {
        baseline.replaceEntities(aliceCase.id(), "facts", List.of(
                Map.of("id", "f1", "key", "k1", "value", "v1", "verificationStatus", "candidate"),
                Map.of("id", "f2", "key", "k2", "value", "v2", "verificationStatus", "conflicted")));
        UUID v1 = baseline.createDraftVersion(aliceCase.id(), alice);
        baseline.confirm(aliceCase.id(), v1, null, alice);

        Map<String, Object> detail = baseline.versionDetail(aliceCase.id(), v1);
        @SuppressWarnings("unchecked")
        List<Object> items = (List<Object>)
                ((Map<String, Object>) detail.get("payload")).get("items");
        @SuppressWarnings("unchecked")
        Map<String, Object> f1 = (Map<String, Object>) items.get(0);
        // 确认 FactsVersion 不把条目 verificationStatus 批量改写为 confirmed（计划 §P2）
        assertEquals("candidate", f1.get("verificationStatus"));
    }

    // ---------- fixtures ----------

    private void seedAllEntities(String caseId) {
        jdbc.update("""
                INSERT INTO app.case_actor(case_id, external_id, actor_type, name, role)
                VALUES (?::uuid, 'act-1', 'natural_person', '张某', '嫌疑人')
                """, caseId);
        jdbc.update("""
                INSERT INTO app.case_event(case_id, external_id, event_date, stage, description)
                VALUES (?::uuid, 'ev-1', '2026-01-01', 'investigation', '作案')
                """, caseId);
        jdbc.update("""
                INSERT INTO app.case_evidence(case_id, external_id, evidence_type, label)
                VALUES (?::uuid, 'evi-1', 'document', '银行流水')
                """, caseId);
        jdbc.update("""
                INSERT INTO app.case_amount(case_id, external_id, kind, label, value)
                VALUES (?::uuid, 'amt-1', 'illegal_gain', '违法所得', 5000)
                """, caseId);
        jdbc.update("""
                INSERT INTO app.case_jurisdiction_connection(case_id, external_id, connection_type, value)
                VALUES (?::uuid, 'jc-1', 'conduct_place', 'CN')
                """, caseId);
        jdbc.update("""
                INSERT INTO app.case_fact(case_id, external_id, fact_key, fact_value)
                VALUES (?::uuid, 'f-1', 'k1', 'v1')
                """, caseId);
    }

    private long count(String table, String caseId) {
        Long n = jdbc.queryForObject(
                "SELECT COUNT(*) FROM app." + table + " WHERE case_id = ?::uuid", Long.class, caseId);
        return n == null ? 0 : n;
    }

    private UUID insertAccount(String username) {
        UUID id = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """, id, username, username, username, "hash");
        return id;
    }

    private static String shortId() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 8);
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
