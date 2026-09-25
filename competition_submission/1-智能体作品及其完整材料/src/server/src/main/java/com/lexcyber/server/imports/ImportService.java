package com.lexcyber.server.imports;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.CaseCreate;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
import com.lexcyber.server.domain.DocumentPolicies;
import com.lexcyber.server.domain.DocumentService;
import com.lexcyber.server.domain.DocumentView;
import com.lexcyber.server.domain.FactService;
import com.lexcyber.server.domain.FactUpdate;
import com.lexcyber.server.domain.FactView;
import com.lexcyber.server.domain.ModuleStateService;
import com.lexcyber.server.domain.ModuleStateUpdate;
import com.lexcyber.server.domain.ModuleStateView;
import com.lexcyber.server.engine.EngineImportClient;
import com.lexcyber.server.review.ReviewOpen;
import com.lexcyber.server.review.ReviewService;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ImportService {
    private static final Logger log = LoggerFactory.getLogger(ImportService.class);
    private static final List<String> APPLY_STEPS = List.of(
            "case.create", "documents.upload", "events.bind", "facts.write", "modules.write", "review.open");

    private final ImportStore store;
    private final RawPackageStorage rawPackages;
    private final EngineImportClient engine;
    private final CaseService cases;
    private final DocumentService documents;
    private final FactService facts;
    private final ModuleStateService modules;
    private final ReviewService reviews;
    private final TransactionTemplate transactions;

    public ImportService(ImportStore store, RawPackageStorage rawPackages,
                         EngineImportClient engine, CaseService cases,
                         DocumentService documents, FactService facts,
                         ModuleStateService modules, ReviewService reviews,
                         PlatformTransactionManager transactionManager) {
        this.store = store;
        this.rawPackages = rawPackages;
        this.engine = engine;
        this.cases = cases;
        this.documents = documents;
        this.facts = facts;
        this.modules = modules;
        this.reviews = reviews;
        this.transactions = new TransactionTemplate(transactionManager);
    }

    public ImportBatchView createUploadedBatch(UUID ownerAccountId, ImportBatchCreate request) {
        requireOwner(ownerAccountId);
        if (request == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "import request is required");
        }
        UUID batchId = UUID.randomUUID();
        byte[] snapshot = ImportPolicies.requireRawPackage(request.data());
        RawPackageStorage.StoredRawPackage raw = rawPackages.describe(
                ownerAccountId, batchId, request.originalFilename(), request.contentType(), snapshot);
        transactions.executeWithoutResult(ignored ->
                store.insertBatchReservation(ownerAccountId, batchId, raw, request.metadata()));
        try {
            rawPackages.put(raw, snapshot);
        } catch (RuntimeException storageError) {
            bestEffortDelete(raw.storageKey());
            try {
                transactions.executeWithoutResult(ignored -> store.markBatchUploadFailed(
                        ownerAccountId, batchId, error("IMPORT_PACKAGE_STORAGE_FAILED", storageError)));
            } catch (RuntimeException statusError) {
                log.warn("failed to mark import batch {} after raw package storage failure", batchId, statusError);
            }
            Arrays.fill(snapshot, (byte) 0);
            throw storageError;
        }
        try {
            return Objects.requireNonNull(transactions.execute(ignored -> {
                store.markBatchUploaded(ownerAccountId, batchId);
                ImportBatchView created = store.requireOwnedBatch(ownerAccountId, batchId);
                store.auditBatchCreated(ownerAccountId, created);
                return created;
            }));
        } finally {
            Arrays.fill(snapshot, (byte) 0);
        }
    }

    @Transactional(readOnly = true)
    public ImportBatchView get(UUID ownerAccountId, UUID batchId) {
        requireOwner(ownerAccountId);
        return store.requireOwnedBatch(ownerAccountId, batchId);
    }

    @Transactional(readOnly = true)
    public List<ImportBatchView> list(UUID ownerAccountId, int page, int size) {
        requirePage(ownerAccountId, page, size);
        return store.listOwnedBatches(ownerAccountId, size, page * size);
    }

    @Transactional(readOnly = true)
    public long count(UUID ownerAccountId) {
        requireOwner(ownerAccountId);
        return store.countOwnedBatches(ownerAccountId);
    }

    @Transactional(readOnly = true)
    public List<ImportItemView> listItems(UUID ownerAccountId, UUID batchId, int page, int size) {
        requirePage(ownerAccountId, page, size);
        return store.listOwnedItems(ownerAccountId, batchId, size, page * size);
    }

    @Transactional(readOnly = true)
    public long countItems(UUID ownerAccountId, UUID batchId) {
        requireOwner(ownerAccountId);
        return store.countOwnedItems(ownerAccountId, batchId);
    }

    @Transactional(readOnly = true)
    public List<ImportStepView> listSteps(UUID ownerAccountId, UUID batchId, UUID itemId) {
        requireOwner(ownerAccountId);
        return store.listOwnedSteps(ownerAccountId, batchId, itemId);
    }

    public ImportBatchView validateBatch(UUID ownerAccountId, UUID batchId) {
        requireOwner(ownerAccountId);
        ImportBatchView current = store.requireOwnedBatch(ownerAccountId, batchId);
        if (List.of("review_required", "approved", "applying", "completed", "partially_completed").contains(current.status())) {
            return current;
        }
        if (!List.of("uploaded", "validation_failed").contains(current.status())) {
            throw statusConflict(current.status(), "validate");
        }
        transactions.executeWithoutResult(ignored ->
                store.casBatchStatus(ownerAccountId, batchId, current.status(), "validating"));

        EngineImportClient.ValidationResponse validation;
        try {
            validation = engine.validate(current.storageKey(), current.rawSha256());
        } catch (RuntimeException ex) {
            markValidationFailure(ownerAccountId, batchId, error("ENGINE_UNAVAILABLE", ex));
            throw ex;
        }
        if (!validation.valid()) {
            Map<String, Object> failure = new LinkedHashMap<>();
            failure.put("code", "IMPORT_VALIDATION_FAILED");
            failure.put("errors", validation.errors() == null ? List.of() : validation.errors());
            markValidationFailure(ownerAccountId, batchId, failure);
            return store.requireOwnedBatch(ownerAccountId, batchId);
        }

        try {
            transactions.executeWithoutResult(ignored -> persistValidation(
                    ownerAccountId, batchId, validation));
        } catch (DataIntegrityViolationException ex) {
            Map<String, Object> failure = error("IMPORT_RELEASE_CONFLICT", ex);
            markValidationFailure(ownerAccountId, batchId, failure);
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_RELEASE_CONFLICT",
                    "同一生产方、包和版本已存在另一导入批次", ex);
        } catch (RuntimeException ex) {
            markValidationFailure(ownerAccountId, batchId, error("IMPORT_VALIDATION_PERSIST_FAILED", ex));
            throw ex;
        }
        return store.requireOwnedBatch(ownerAccountId, batchId);
    }

    public ImportBatchView approve(UUID ownerAccountId, UUID batchId, UUID actorAccountId) {
        requireOwner(ownerAccountId);
        requireOwner(actorAccountId);
        List<ImportItemView> items = store.listOwnedItems(ownerAccountId, batchId);
        if (items.isEmpty()) {
            throw statusConflict("review_required", "approve empty import");
        }
        boolean blocked = items.stream().anyMatch(item ->
                List.of("conflict", "invalid", "failed").contains(item.status()));
        if (blocked) {
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_HAS_CONFLICTS",
                    "导入批次仍有冲突或无效条目，不能批准");
        }
        transactions.executeWithoutResult(ignored -> {
            store.approveReviewableItems(ownerAccountId, batchId);
            store.approveBatch(ownerAccountId, batchId, actorAccountId);
            store.audit(ownerAccountId, batchId, "import.batch.approved", Map.of());
        });
        return store.requireOwnedBatch(ownerAccountId, batchId);
    }

    public ImportBatchView apply(UUID ownerAccountId, UUID batchId) {
        requireOwner(ownerAccountId);
        ImportBatchView batch = store.requireOwnedBatch(ownerAccountId, batchId);
        if ("completed".equals(batch.status())) return batch;
        if ("applying".equals(batch.status())) {
            transactions.executeWithoutResult(ignored -> store.recoverExpiredApply(ownerAccountId, batchId));
            batch = store.requireOwnedBatch(ownerAccountId, batchId);
        }
        if (!"approved".equals(batch.status())) {
            throw statusConflict(batch.status(), "apply");
        }
        UUID leaseToken = Objects.requireNonNull(transactions.execute(
                ignored -> store.claimApplyLease(ownerAccountId, batchId)));
        ImportBatchView applyingBatch = batch;
        transactions.executeWithoutResult(ignored ->
                store.audit(ownerAccountId, batchId, "import.batch.apply_started", Map.of()));

        List<ImportItemView> items = store.listOwnedItems(ownerAccountId, batchId);
        boolean needsArchive = items.stream().anyMatch(item -> "approved".equals(item.status()));
        ImportArchiveReader archive = null;
        int succeeded = 0;
        int failed = 0;
        List<Map<String, Object>> failures = new ArrayList<>();
        try {
            if (needsArchive) archive = new ImportArchiveReader(readRawPackage(ownerAccountId, batchId));
            for (ImportItemView item : items) {
                transactions.executeWithoutResult(ignored -> store.renewApplyLease(ownerAccountId, batchId, leaseToken));
                if ("no_op".equals(item.status()) || "applied".equals(item.status())) {
                    succeeded++;
                    continue;
                }
                if (!"approved".equals(item.status())) {
                    failed++;
                    failures.add(Map.of("itemId", item.itemId(), "status", item.status()));
                    continue;
                }
                try {
                    applyItem(ownerAccountId, applyingBatch, item, Objects.requireNonNull(archive), leaseToken);
                    succeeded++;
                } catch (RuntimeException ex) {
                    failed++;
                    Map<String, Object> itemError = error("IMPORT_ITEM_APPLY_FAILED", ex);
                    failures.add(Map.of("itemId", item.itemId(), "error", itemError));
                    ImportItemView latest = store.requireOwnedItem(ownerAccountId, batchId, item.id());
                    if ("applying".equals(latest.status())) {
                        transactions.executeWithoutResult(ignored -> store.setItemStatus(
                                ownerAccountId, batchId, item.id(), leaseToken, "applying", "failed", latest.caseId(), itemError));
                    }
                }
            }
        } finally {
            if (archive != null) archive.clear();
        }
        boolean noFailures = failed == 0;
        String finalStatus = noFailures ? "completed" : (succeeded > 0 ? "partially_completed" : "failed");
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("succeeded", succeeded);
        summary.put("failed", failed);
        summary.put("failures", failures);
        transactions.executeWithoutResult(ignored -> {
            store.finishBatch(ownerAccountId, batchId, leaseToken, finalStatus, noFailures ? Map.of() : summary);
            store.audit(ownerAccountId, batchId, "import.batch." + finalStatus, summary);
        });
        return store.requireOwnedBatch(ownerAccountId, batchId);
    }

    public ImportBatchView retry(UUID ownerAccountId, UUID batchId) {
        requireOwner(ownerAccountId);
        ImportBatchView batch = store.requireOwnedBatch(ownerAccountId, batchId);
        if ("validation_failed".equals(batch.status())) {
            return validateBatch(ownerAccountId, batchId);
        }
        if ("applying".equals(batch.status())) {
            transactions.executeWithoutResult(ignored -> store.recoverExpiredApply(ownerAccountId, batchId));
            return apply(ownerAccountId, batchId);
        }
        if (!List.of("failed", "partially_completed").contains(batch.status()) || batch.approvedAt() == null) {
            throw statusConflict(batch.status(), "retry");
        }
        transactions.executeWithoutResult(ignored -> {
            store.resetFailedSteps(ownerAccountId, batchId);
            store.resetFailedItems(ownerAccountId, batchId);
            store.casBatchStatus(ownerAccountId, batchId, batch.status(), "approved");
            store.audit(ownerAccountId, batchId, "import.batch.retried", Map.of());
        });
        return apply(ownerAccountId, batchId);
    }

    public byte[] readRawPackage(UUID ownerAccountId, UUID batchId) {
        requireOwner(ownerAccountId);
        ImportBatchView batch = store.requireOwnedBatch(ownerAccountId, batchId);
        byte[] data = rawPackages.get(batch.storageKey());
        if (data.length != batch.sizeBytes() || !ImportPolicies.sha256(data).equals(batch.rawSha256())) {
            Arrays.fill(data, (byte) 0);
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "IMPORT_PACKAGE_CORRUPTED",
                    "导入原包与持久化摘要不一致");
        }
        return data;
    }

    private void persistValidation(UUID ownerAccountId, UUID batchId,
                                   EngineImportClient.ValidationResponse validation) {
        store.deleteItemsForValidation(ownerAccountId, batchId);
        List<Map<String, Object>> normalizedItems = validation.items() == null ? List.of() : validation.items();
        int ordinal = 0;
        for (Map<String, Object> normalized : normalizedItems) {
            String itemId = string(normalized, "item_id");
            String externalCaseId = string(normalized, "external_case_id");
            String payloadPath = string(normalized, "payload_path");
            String payloadSha256 = string(normalized, "payload_sha256");
            UUID id = UUID.randomUUID();
            ImportItemView created = store.insertItem(ownerAccountId, new ImportItemCreate(
                    id, batchId, ordinal++, itemId, externalCaseId, payloadPath, payloadSha256,
                    Map.of("plan", normalized)));
            Optional<ExternalResourceMappingView> existing = store.findMapping(
                    ownerAccountId, validation.producerId(), validation.datasetId(), "case", externalCaseId);
            String action;
            String status;
            String caseId = null;
            if (existing.isEmpty()) {
                action = "create";
                status = "review_required";
            } else if (payloadSha256.equals(existing.get().sourceSha256())
                    && hasAllDocumentMappings(ownerAccountId, validation, normalized)) {
                action = "no_op";
                status = "no_op";
                caseId = existing.get().caseId();
            } else {
                action = "conflict";
                status = "conflict";
                caseId = existing.get().caseId();
            }
            Map<String, Object> diff = new LinkedHashMap<>();
            diff.put("action", action);
            if (caseId != null) diff.put("existingCaseId", caseId);
            store.setItemDiff(ownerAccountId, batchId, created.id(), status, diff, caseId);
        }
        store.finishValidationSuccess(ownerAccountId, batchId,
                validation.schemaVersion(), validation.packageId(), validation.producerId(),
                validation.datasetId(), validation.revision(), validation.packageDigest());
        store.audit(ownerAccountId, batchId, "import.batch.validated",
                Map.of("itemCount", normalizedItems.size()));
    }

    private boolean hasAllDocumentMappings(UUID ownerAccountId,
                                           EngineImportClient.ValidationResponse validation,
                                           Map<String, Object> normalized) {
        Object value = normalized.get("files");
        if (!(value instanceof List<?> files)) return false;
        for (Object row : files) {
            if (!(row instanceof Map<?, ?> raw) || !(raw.get("document_id") instanceof String documentId)
                    || !(raw.get("sha256") instanceof String sha256)) return false;
            Optional<ExternalResourceMappingView> mapping = store.findMapping(
                    ownerAccountId, validation.producerId(), validation.datasetId(), "document", documentId);
            if (mapping.isEmpty() || !sha256.equals(mapping.get().sourceSha256())) return false;
        }
        return true;
    }

    private void applyItem(UUID ownerAccountId, ImportBatchView batch,
                           ImportItemView item, ImportArchiveReader archive, UUID leaseToken) {
        transactions.executeWithoutResult(ignored -> store.setItemStatus(
                ownerAccountId, batch.id(), item.id(), leaseToken, "approved", "applying", item.caseId(), Map.of()));
        ImportPlanProjector projector = new ImportPlanProjector(plan(item));

        Map<String, Object> caseOutput = runStep(ownerAccountId, batch.id(), item.id(), leaseToken, "case.create", 0,
                () -> Map.of("caseId", ensureCase(ownerAccountId, batch, item, projector.caseCreate()).id()));
        String caseId = requiredOutputString(caseOutput, "caseId", "case.create");
        cases.requireOwned(ownerAccountId, caseId);
        transactions.executeWithoutResult(ignored -> store.setItemStatus(
                ownerAccountId, batch.id(), item.id(), leaseToken, "applying", "applying", caseId, Map.of()));

        Map<String, Object> documentOutput = runStep(ownerAccountId, batch.id(), item.id(), leaseToken, "documents.upload", 1,
                () -> Map.of("documentIds", ensureDocuments(
                        ownerAccountId, batch, item, caseId, projector.files(), archive)));
        Map<String, String> documentIds = requiredOutputStringMap(documentOutput, "documentIds", "documents.upload");
        runStep(ownerAccountId, batch.id(), item.id(), leaseToken, "events.bind", 2,
                () -> Map.of("bound", bindEvents(ownerAccountId, caseId, projector.eventBindings(documentIds))));
        runStep(ownerAccountId, batch.id(), item.id(), leaseToken, "facts.write", 3,
                () -> Map.of("items", writeFacts(ownerAccountId, caseId, projector.facts(documentIds))));
        runStep(ownerAccountId, batch.id(), item.id(), leaseToken, "modules.write", 4,
                () -> writeModules(ownerAccountId, caseId, projector));
        runStep(ownerAccountId, batch.id(), item.id(), leaseToken, "review.open", 5,
                () -> Map.of("reviewId", openReview(ownerAccountId, caseId)));
        transactions.executeWithoutResult(ignored -> store.setItemStatus(
                ownerAccountId, batch.id(), item.id(), leaseToken, "applying", "applied", caseId, Map.of()));
    }

    private CaseView ensureCase(UUID ownerAccountId, ImportBatchView batch,
                                ImportItemView item, CaseCreate request) {
        Optional<ExternalResourceMappingView> mapped = store.findMapping(
                ownerAccountId, batch.producerId(), batch.datasetId(), "case", item.externalCaseId());
        if (mapped.isPresent()) {
            if (!item.payloadSha256().equals(mapped.get().sourceSha256())) {
                throw new ApiException(HttpStatus.CONFLICT, "IMPORT_PAYLOAD_CONFLICT",
                        "外部案件身份已映射到不同 payload 版本");
            }
            return cases.requireOwned(ownerAccountId, mapped.get().caseId());
        }
        String key = stableKey("case", batch.producerId(), batch.datasetId(), item.externalCaseId());
        CaseView created = cases.create(ownerAccountId, request, key);
        transactions.executeWithoutResult(ignored -> store.upsertMapping(ownerAccountId,
                new ExternalResourceMappingCreate(
                        UUID.randomUUID(), batch.id(), item.id(), batch.producerId(), batch.datasetId(),
                        "case", item.externalCaseId(), "case", created.id(), created.id(), null,
                        batch.revision(), item.payloadSha256(), batch.revision(), Map.of())));
        return created;
    }

    private Map<String, String> ensureDocuments(UUID ownerAccountId, ImportBatchView batch,
                                                ImportItemView item, String caseId,
                                                List<ImportPlanProjector.FilePlan> files,
                                                ImportArchiveReader archive) {
        Map<String, String> result = new LinkedHashMap<>();
        for (ImportPlanProjector.FilePlan file : files) {
            Optional<ExternalResourceMappingView> mapped = store.findMapping(
                    ownerAccountId, batch.producerId(), batch.datasetId(), "document", file.documentId());
            DocumentView document;
            if (mapped.isPresent()) {
                if (!file.sha256().equals(mapped.get().sourceSha256())) {
                    throw new ApiException(HttpStatus.CONFLICT, "IMPORT_DOCUMENT_CONFLICT",
                            "外部材料已映射到不同内容");
                }
                document = documents.requireOwned(ownerAccountId, mapped.get().documentId());
                if (!caseId.equals(document.caseId())) {
                    throw new ApiException(HttpStatus.CONFLICT, "IMPORT_DOCUMENT_CONFLICT", "材料映射不属于目标案件");
                }
            } else {
                byte[] data = archive.require(file.path(), file.size(), file.sha256());
                String role = "case_material".equals(file.role())
                        ? DocumentPolicies.ROLE_INPUT : DocumentPolicies.ROLE_ANNOTATION;
                document = documents.upload(ownerAccountId, caseId, filename(file.path()),
                        file.mediaType(), data, role,
                        stableKey("document", batch.producerId(), batch.datasetId(), file.documentId()));
                Arrays.fill(data, (byte) 0);
                DocumentView stored = document;
                transactions.executeWithoutResult(ignored -> store.upsertMapping(ownerAccountId,
                        new ExternalResourceMappingCreate(
                                UUID.randomUUID(), batch.id(), item.id(), batch.producerId(), batch.datasetId(),
                                "document", file.documentId(), "document", stored.id(), caseId, stored.id(),
                                batch.revision(), file.sha256(), file.sourceVersion(), Map.of())));
            }
            result.put(file.documentId(), document.id());
        }
        return result;
    }

    private int bindEvents(UUID ownerAccountId, String caseId,
                           List<ImportPlanProjector.EventBinding> bindings) {
        for (ImportPlanProjector.EventBinding binding : bindings) {
            cases.bindEventDocument(ownerAccountId, caseId, binding.eventId(), binding.update());
        }
        return bindings.size();
    }

    private int writeFacts(UUID ownerAccountId, String caseId,
                           List<com.lexcyber.server.domain.FactItem> expected) {
        FactView current = facts.get(ownerAccountId, caseId);
        if (current.items().isEmpty()) {
            facts.replace(ownerAccountId, caseId, new FactUpdate(expected));
        } else if (!current.items().equals(expected)) {
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_FACTS_CONFLICT", "现有案件事实与导入包不同");
        }
        return expected.size();
    }

    private Map<String, Object> writeModules(UUID ownerAccountId, String caseId,
                                             ImportPlanProjector projector) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String module : List.of("compliance", "conviction")) {
            ModuleStateView current = modules.get(ownerAccountId, caseId, module);
            ModuleStateUpdate expected = projector.moduleState(module, current.version());
            ModuleStateView written;
            if (current.version() == 0 && current.content().isEmpty()) {
                written = modules.replace(ownerAccountId, caseId, module, expected);
            } else if (current.applicability().equals(expected.applicability())
                    && current.content().equals(expected.content())
                    && Objects.equals(current.sourceVersion(), expected.sourceVersion())
                    && !current.factsStale()) {
                written = current;
            } else {
                throw new ApiException(HttpStatus.CONFLICT, "IMPORT_MODULE_CONFLICT",
                        "现有模块内容与导入包不同: " + module);
            }
            result.put(module + "Version", written.version());
        }
        return result;
    }

    private String openReview(UUID ownerAccountId, String caseId) {
        ModuleStateView conviction = modules.get(ownerAccountId, caseId, "conviction");
        Map<String, Object> review = reviews.open(ownerAccountId, caseId,
                new ReviewOpen("conviction", null, null, "conviction",
                        conviction.version(), null, null, null),
                stableKey("review", caseId, "conviction", String.valueOf(conviction.version())));
        return String.valueOf(review.get("id"));
    }

    private Map<String, Object> runStep(UUID ownerAccountId, UUID batchId, UUID itemId, UUID leaseToken,
                                        String stepKey, int ordinal,
                                        Supplier<Map<String, Object>> action) {
        ImportStepView step = Objects.requireNonNull(transactions.execute(ignored -> store.ensureStep(ownerAccountId,
                new ImportStepCreate(UUID.randomUUID(), batchId, itemId, stepKey, ordinal, Map.of()))));
        if ("completed".equals(step.status())) {
            return requiredStepOutput(step, stepKey);
        }
        try {
            return Objects.requireNonNull(transactions.execute(ignored -> {
                store.lockApplyLease(ownerAccountId, batchId, leaseToken);
                store.claimStep(ownerAccountId, batchId, step.id(), leaseToken);
                Map<String, Object> result = action.get();
                store.completeStep(ownerAccountId, batchId, step.id(), leaseToken, result);
                store.renewApplyLease(ownerAccountId, batchId, leaseToken);
                return result;
            }));
        } catch (RuntimeException ex) {
            try {
                transactions.executeWithoutResult(ignored ->
                        store.markStepFailure(ownerAccountId, batchId, step.id(), leaseToken,
                                error("IMPORT_STEP_FAILED", ex)));
            } catch (RuntimeException statusError) {
                log.warn("failed to mark import step {} as failed", step.id(), statusError);
            }
            throw ex;
        }
    }

    private static Map<String, Object> requiredStepOutput(ImportStepView step, String stepKey) {
        if (step.output() == null || step.output().isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_STEP_OUTPUT_MISSING",
                    "completed import step has no recoverable output: " + stepKey);
        }
        return step.output();
    }

    private static String requiredOutputString(Map<String, Object> output, String key, String stepKey) {
        Object value = output.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_STEP_OUTPUT_INVALID",
                    "completed import step output is invalid: " + stepKey);
        }
        return text;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, String> requiredOutputStringMap(Map<String, Object> output,
                                                                String key, String stepKey) {
        Object value = output.get(key);
        if (!(value instanceof Map<?, ?> raw)) {
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_STEP_OUTPUT_INVALID",
                    "completed import step output is invalid: " + stepKey);
        }
        Map<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String externalId)
                    || !(entry.getValue() instanceof String documentId)
                    || externalId.isBlank() || documentId.isBlank()) {
                throw new ApiException(HttpStatus.CONFLICT, "IMPORT_STEP_OUTPUT_INVALID",
                        "completed import step output is invalid: " + stepKey);
            }
            result.put(externalId, documentId);
        }
        return Map.copyOf(result);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> plan(ImportItemView item) {
        Object value = item.metadata().get("plan");
        if (!(value instanceof Map<?, ?> raw)) {
            throw new ApiException(HttpStatus.CONFLICT, "IMPORT_PLAN_MISSING", "导入条目缺少规范化计划");
        }
        return (Map<String, Object>) raw;
    }

    private void markValidationFailure(UUID ownerAccountId, UUID batchId, Map<String, Object> error) {
        try {
            transactions.executeWithoutResult(ignored -> {
                store.finishValidationFailure(ownerAccountId, batchId, error);
                store.audit(ownerAccountId, batchId, "import.batch.validation_failed", error);
            });
        } catch (RuntimeException statusError) {
            log.warn("failed to persist validation failure for import batch {}", batchId, statusError);
        }
    }

    private void bestEffortDelete(String storageKey) {
        try {
            rawPackages.delete(storageKey);
        } catch (RuntimeException deleteError) {
            log.warn("failed to delete raw import package {} after storage failure", storageKey, deleteError);
        }
    }

    private static String stableKey(String kind, String... parts) {
        String value = kind + ":" + String.join(":", parts);
        return "import-" + kind + "-" + DocumentPolicies.sha256Hex(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String filename(String path) {
        int slash = path.lastIndexOf('/');
        return slash < 0 ? path : path.substring(slash + 1);
    }

    private static String string(Map<String, Object> value, String key) {
        Object item = value.get(key);
        if (!(item instanceof String text) || text.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "IMPORT_PLAN_INVALID", key + " is required");
        }
        return text;
    }

    private static Map<String, Object> error(String code, Throwable error) {
        return Map.of("code", code, "message", "import operation failed");
    }

    private static ApiException statusConflict(String status, String action) {
        return new ApiException(HttpStatus.CONFLICT, "IMPORT_STATUS_CONFLICT",
                "cannot " + action + " import batch in status " + status);
    }

    private static void requirePage(UUID ownerAccountId, int page, int size) {
        requireOwner(ownerAccountId);
        if (page < 0 || size < 1 || size > 100) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "invalid page");
        }
    }

    private static void requireOwner(UUID ownerAccountId) {
        if (ownerAccountId == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "session required");
        }
    }
}
