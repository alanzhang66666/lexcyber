package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;

/** Date binding checks shared by v2 module confirmation and draft approval. */
class LegalAnalysisContextTest {
    private static final String EXTERNAL_JDBC = System.getenv("TEST_JDBC_URL");
    private static PostgreSQLContainer<?> postgres;

    private JdbcTemplate jdbc;
    private UUID account;
    private UUID caseId;

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
        if (postgres != null) postgres.stop();
    }

    @BeforeEach
    void setup() {
        DataSource dataSource = dataSource();
        Flyway.configure().dataSource(dataSource).schemas("app")
                .locations("classpath:db/migration/app").load().migrate();
        jdbc = new JdbcTemplate(dataSource);
        account = UUID.randomUUID();
        caseId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                VALUES (?, ?, ?, 'Date test', 'hash')
                """, account, "date_" + account, "date_" + account);
    }

    @Test
    void confirmationRejectsV2ArtifactWhenCaseDateIsMissing() {
        insertCase(null);
        UUID version = insertModuleArtifact("case.compliance.v2", "2026-09-06");
        insertModuleHead("compliance", version);

        ApiException error = assertThrows(ApiException.class,
                () -> new ModuleConfirmationService(jdbc).confirm(caseId.toString(), "compliance", account));

        assertEquals("DEPENDENCY_STALE", error.code());
    }

    @Test
    void confirmationRejectsPreviouslyCalculatedLegalDivergence() {
        insertCase("2026-09-06");
        UUID version = insertModuleArtifact("case.compliance.v2", "2026-09-06",
                "{\"divergence\":[{\"code\":\"LAW_VERSION_DIVERGENCE\"}],"
                        + "\"input_validation\":{\"schema_version\":\"case.input-validation.v1\","
                        + "\"status\":\"verified\",\"checks\":[],\"blockers\":[]}}");
        insertModuleHead("compliance", version);

        ApiException error = assertThrows(ApiException.class,
                () -> new ModuleConfirmationService(jdbc).confirm(caseId.toString(), "compliance", account));

        assertEquals("MODULE_BLOCKED", error.code());
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.module_head WHERE case_id = ? AND confirmed_version_id IS NOT NULL",
                Integer.class, caseId));
    }

    @Test
    void confirmationRejectsDamagedFrozenProofsEvenWhenWorkingCopyContainsEvidence() {
        insertCase("2026-09-06");
        FactsBaselineService baseline = new FactsBaselineService(jdbc, new StalePropagationService(jdbc));
        baseline.replaceEntities(caseId.toString(), "evidence", java.util.List.of(
                java.util.Map.of("id", "live-proof", "type", "document")));
        UUID version = insertModuleArtifact("case.compliance.v2", "2026-09-06");
        insertModuleHead("compliance", version);
        String damaged = "{\"items\":[{\"key\":\"k\",\"value\":\"v\","
                + "\"evidenceIds\":[\"live-proof\"]}],\"entities\":{\"evidence\":[]}}";
        UUID facts = bindConfirmedFacts(version, damaged);

        ApiException error = assertThrows(ApiException.class,
                () -> new ModuleConfirmationService(jdbc).confirm(caseId.toString(), "compliance", account));

        assertEquals("FACTS_REFERENCE_INVALID", error.code());
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.module_head WHERE case_id = ? AND confirmed_version_id IS NOT NULL",
                Integer.class, caseId));
        assertEquals(facts, jdbc.queryForObject("SELECT confirmed_facts_version_id FROM app.facts_head WHERE case_id = ?",
                UUID.class, caseId));
        assertEquals(Boolean.TRUE, jdbc.queryForObject("SELECT payload = ?::jsonb FROM app.facts_version WHERE facts_version_id = ?",
                Boolean.class, damaged, facts));
    }

    @Test
    void confirmationUsesValidFrozenEvidenceAfterWorkingCopyEvidenceWasRemoved() {
        insertCase("2026-09-06");
        UUID version = insertModuleArtifact("case.compliance.v2", "2026-09-06");
        insertModuleHead("compliance", version);
        UUID proof = UUID.randomUUID();
        String frozen = "{\"items\":[{\"key\":\"k\",\"value\":\"v\",\"evidenceIds\":[\""
                + proof + "\"]}],\"entities\":{\"evidence\":[{\"entityId\":\""
                + proof + "\",\"id\":\"archived-proof\",\"verificationStatus\":\"confirmed\"}]}}";
        bindConfirmedFacts(version, frozen);
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM app.case_evidence WHERE case_id = ?",
                Integer.class, caseId));

        assertEquals(version, new ModuleConfirmationService(jdbc)
                .confirm(caseId.toString(), "compliance", account));
    }

    @Test
    void requireCurrentRejectsMalformedDirectAndRecursiveInputValidationMarkers() {
        insertCase("2026-09-06");
        String[] malformed = {
                "{}",
                "{\"input_validation\":null}",
                "{\"input_validation\":{\"schema_version\":\"wrong\",\"status\":\"verified\",\"checks\":[],\"blockers\":[]}}",
                "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"blocked\",\"checks\":[],\"blockers\":[{}]}}",
                "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[],\"blockers\":[{}]}}",
                "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":{},\"blockers\":[]}}",
                "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[null],\"blockers\":[]}}"
        };
        for (String payload : malformed) {
            UUID upstream = insertArtifact("compliance", "case.compliance.v2", payload);
            UUID downstream = insertArtifact("sentencing", "sentencing.v2", validInputValidation());
            jdbc.update("UPDATE app.artifact_stream SET scope_key = ? WHERE artifact_stream_id = "
                            + "(SELECT artifact_stream_id FROM app.artifact_version WHERE artifact_version_id = ?)",
                    "module:compliance:" + upstream, upstream);
            jdbc.update("UPDATE app.artifact_stream SET scope_key = ? WHERE artifact_stream_id = "
                            + "(SELECT artifact_stream_id FROM app.artifact_version WHERE artifact_version_id = ?)",
                    "module:sentencing:" + downstream, downstream);
            jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?)",
                    downstream, upstream);
            ApiException error = assertThrows(ApiException.class,
                    () -> LegalAnalysisContext.requireCurrent(jdbc, caseId.toString(), downstream));
            assertEquals("DEPENDENCY_STALE", error.code());
        }
    }

    @Test
    void requireCurrentAllowsVerifiedInputValidationMarker() {
        insertCase("2026-09-06");
        UUID version = insertArtifact("compliance", "case.compliance.v2", validInputValidation());
        LegalAnalysisContext.requireCurrent(jdbc, caseId.toString(), version);
    }

    @Test
    void requireCurrentRejectsForeignArtifactInFullDependencyClosure() {
        insertCase("2026-09-06");
        UUID foreignCase = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json)
                VALUES (?, ?, 'Foreign test', 'CN', '2026-09-06', '{}'::jsonb)
                """, foreignCase, account);
        UUID root = insertArtifact("compliance", "case.compliance.v2", validInputValidation());
        UUID foreign = insertArtifactForCase(foreignCase, "conviction", "case.conviction.v2", "{}");
        jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?)",
                root, foreign);

        ApiException error = assertThrows(ApiException.class,
                () -> LegalAnalysisContext.requireCurrent(jdbc, caseId.toString(), root));
        assertEquals("DEPENDENCY_STALE", error.code());
    }

    @Test
    void requireCurrentRejectsForeignLegacyArtifactToo() {
        insertCase("2026-09-06");
        UUID foreignCase = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json)
                VALUES (?, ?, 'Foreign legacy test', 'CN', '2026-09-06', '{}'::jsonb)
                """, foreignCase, account);
        UUID root = insertArtifact("compliance", "case.compliance.v2", validInputValidation());
        UUID foreign = insertArtifactForCase(foreignCase, "conviction", "case.module.v1", "{}");
        jdbc.update("INSERT INTO app.artifact_artifact_dependency(artifact_version_id, depends_on_artifact_version_id) VALUES (?, ?)",
                root, foreign);

        ApiException error = assertThrows(ApiException.class,
                () -> LegalAnalysisContext.requireCurrent(jdbc, caseId.toString(), root));
        assertEquals("DEPENDENCY_STALE", error.code());
    }

    private UUID bindConfirmedFacts(UUID artifact, String payload) {
        UUID facts = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.facts_version(facts_version_id, case_id, version, content_hash,
                    payload, created_by, confirmed_by, confirmed_at)
                VALUES (?, ?, 1, 'proof-history', ?::jsonb, ?, ?, now())
                """, facts, caseId, payload, account, account);
        jdbc.update("""
                INSERT INTO app.facts_head(case_id, confirmed_facts_version_id)
                VALUES (?, ?) ON CONFLICT (case_id) DO UPDATE
                SET confirmed_facts_version_id = EXCLUDED.confirmed_facts_version_id
                """, caseId, facts);
        jdbc.update("INSERT INTO app.artifact_facts_dependency(artifact_version_id, facts_version_id) VALUES (?, ?)",
                artifact, facts);
        return facts;
    }

    @Test
    void approvalRejectsLateV2CompletionWithOldFrozenDate() {
        insertCase("2026-09-07");
        UUID draftId = UUID.randomUUID();
        UUID streamId = UUID.randomUUID();
        UUID version = UUID.randomUUID();
        jdbc.update("INSERT INTO app.case_drafts(id, case_id, draft_type, updated_by) VALUES (?, ?, 'judgment', ?)",
                draftId, caseId, account);
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                VALUES (?, ?, 'draft', ?, 2)
                """, streamId, caseId, "draft:" + draftId);
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, 'draft.v2', 'calculated', '{}',
                        '{"as_of_date":"2026-09-06","artifacts":[]}', 'late')
                """, version, streamId);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                version, streamId);
        jdbc.update("""
                INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id, stale)
                VALUES (?, ?, ?, NULL, false)
                """, draftId, caseId, streamId);

        ApiException error = assertThrows(ApiException.class,
                () -> new DraftApprovalService(jdbc).approve(caseId.toString(), draftId, account));

        assertEquals("DEPENDENCY_STALE", error.code());
    }

    private void insertCase(String asOfDate) {
        jdbc.update("""
                INSERT INTO app.cases(id, owner_account_id, title, jurisdiction, as_of_date, metadata_json)
                VALUES (?, ?, 'Date test', 'CN', ?::date, '{}'::jsonb)
                """, caseId, account, asOfDate);
    }

    private UUID insertModuleArtifact(String schemaVersion, String asOfDate) {
        return insertModuleArtifact(schemaVersion, asOfDate,
                "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[],\"blockers\":[]}}");
    }

    private UUID insertModuleArtifact(String schemaVersion, String asOfDate, String payload) {
        UUID version = insertArtifact("compliance", schemaVersion, payload, asOfDate);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                version, jdbc.queryForObject("SELECT artifact_stream_id FROM app.artifact_version WHERE artifact_version_id = ?",
                        UUID.class, version));
        return version;
    }

    private UUID insertArtifact(String module, String schemaVersion, String payload) {
        return insertArtifact(module, schemaVersion, payload, "2026-09-06");
    }

    private UUID insertArtifact(String module, String schemaVersion, String payload, String asOfDate) {
        return insertArtifactForCase(caseId, module, schemaVersion, payload, asOfDate);
    }

    private UUID insertArtifactForCase(UUID targetCase, String module, String schemaVersion, String payload) {
        return insertArtifactForCase(targetCase, module, schemaVersion, payload, "2026-09-06");
    }

    private UUID insertArtifactForCase(UUID targetCase, String module, String schemaVersion, String payload, String asOfDate) {
        UUID streamId = UUID.randomUUID();
        UUID version = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key, next_version)
                VALUES (?, ?, ?, ?, 2)
                """, streamId, targetCase, module, "module:" + module);
        jdbc.update("""
                INSERT INTO app.artifact_version(
                    artifact_version_id, artifact_stream_id, version, schema_version,
                    outcome_status, payload, dependency_snapshot, output_hash)
                VALUES (?, ?, 1, ?, 'calculated', ?::jsonb, jsonb_build_object('as_of_date', ?), 'module')
                """, version, streamId, schemaVersion, payload, asOfDate);
        jdbc.update("UPDATE app.artifact_stream SET latest_version_id = ? WHERE artifact_stream_id = ?",
                version, streamId);
        return version;
    }

    private String validInputValidation() {
        return "{\"input_validation\":{\"schema_version\":\"case.input-validation.v1\",\"status\":\"verified\",\"checks\":[],\"blockers\":[]}}";
    }

    private void insertModuleHead(String module, UUID version) {
        UUID streamId = jdbc.queryForObject(
                "SELECT artifact_stream_id FROM app.artifact_version WHERE artifact_version_id = ?",
                UUID.class, version);
        jdbc.update("""
                INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id, stale)
                VALUES (?, ?, ?, NULL, false)
                """, caseId, module, streamId);
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
