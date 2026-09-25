package com.lexcyber.server.imports;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ImportStore {
    private static final String BATCH_SELECT = """
            SELECT id, owner_account_id, schema_version, package_id, producer_id, dataset_id, revision,
                   package_digest, original_filename, content_type, size_bytes, raw_sha256, storage_key,
                   status, metadata_json, error_json, approved_by, approved_at, created_at, updated_at,
                   started_at, completed_at
            FROM app.import_batches
            """;
    private static final String ITEM_SELECT = """
            SELECT i.id, i.batch_id, i.ordinal, i.item_id, i.external_case_id, i.payload_path,
                   i.payload_sha256, i.status, i.case_id, i.diff_json, i.metadata_json, i.error_json,
                   i.created_at, i.updated_at, i.started_at, i.completed_at
            FROM app.import_items i
            """;
    private static final String STEP_SELECT = """
            SELECT s.id, s.batch_id, s.item_id, s.step_key, s.ordinal, s.attempt, s.status,
                   s.input_json, s.output_json, s.error_json, s.created_at, s.updated_at,
                   s.started_at, s.finished_at
            FROM app.import_steps s
            """;
    private static final String MAPPING_SELECT = """
            SELECT m.id, m.owner_account_id, m.batch_id, m.item_id, m.producer_id, m.dataset_id,
                   m.external_resource_type, m.external_resource_id, m.internal_resource_type,
                   m.internal_resource_id, m.case_id, m.document_id, m.first_revision, m.last_revision,
                   m.source_sha256, m.source_version, m.active, m.metadata_json, m.created_at, m.updated_at
            FROM app.external_resource_map m
            """;

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public ImportStore(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public void insertBatchReservation(UUID ownerAccountId, UUID batchId,
                                       RawPackageStorage.StoredRawPackage raw,
                                       Map<String, Object> metadata) {
        jdbc.update("""
                INSERT INTO app.import_batches(
                    id, owner_account_id, original_filename, content_type, size_bytes,
                    raw_sha256, storage_key, status, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'uploading', ?::jsonb)
                """, batchId, ownerAccountId, raw.filename(), raw.contentType(), raw.sizeBytes(),
                raw.sha256(), raw.storageKey(), writeJson(metadata));
    }

    public void markBatchUploaded(UUID ownerAccountId, UUID batchId) {
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'uploaded', updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'uploading'
                """, batchId, ownerAccountId);
        if (changed == 0) throw notFound();
    }

    public void markBatchUploadFailed(UUID ownerAccountId, UUID batchId, Map<String, Object> error) {
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'failed', error_json = ?::jsonb, completed_at = now(), updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'uploading'
                """, writeJson(error), batchId, ownerAccountId);
        if (changed == 0) throw notFound();
    }

    public ImportBatchView requireOwnedBatch(UUID ownerAccountId, UUID batchId) {
        List<ImportBatchView> rows = jdbc.query(
                BATCH_SELECT + " WHERE id = ? AND owner_account_id = ?",
                this::mapBatch, batchId, ownerAccountId);
        if (rows.isEmpty()) {
            throw notFound();
        }
        return rows.get(0);
    }

    public List<ImportBatchView> listOwnedBatches(UUID ownerAccountId, int limit, int offset) {
        return jdbc.query(
                BATCH_SELECT + " WHERE owner_account_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                this::mapBatch, ownerAccountId, limit, offset);
    }

    public long countOwnedBatches(UUID ownerAccountId) {
        Long total = jdbc.queryForObject(
                "SELECT COUNT(*) FROM app.import_batches WHERE owner_account_id = ?",
                Long.class, ownerAccountId);
        return total == null ? 0L : total;
    }

    public ImportItemView insertItem(UUID ownerAccountId, ImportItemCreate item) {
        int changed = jdbc.update("""
                INSERT INTO app.import_items(
                    id, owner_account_id, batch_id, ordinal, item_id, external_case_id, payload_path,
                    payload_sha256, status, metadata_json)
                SELECT ?, b.owner_account_id, b.id, ?, ?, ?, ?, ?, 'pending', ?::jsonb
                FROM app.import_batches b
                WHERE b.id = ? AND b.owner_account_id = ?
                """, item.id(), item.ordinal(), item.itemId(), item.externalCaseId(),
                item.payloadPath(), item.payloadSha256(), writeJson(item.metadata()),
                item.batchId(), ownerAccountId);
        if (changed == 0) throw notFound();
        return requireOwnedItem(ownerAccountId, item.batchId(), item.id());
    }

    public ImportItemView requireOwnedItem(UUID ownerAccountId, UUID batchId, UUID itemId) {
        List<ImportItemView> rows = jdbc.query(
                ITEM_SELECT + " JOIN app.import_batches b ON b.id = i.batch_id"
                        + " WHERE i.id = ? AND i.batch_id = ? AND b.owner_account_id = ?",
                this::mapItem, itemId, batchId, ownerAccountId);
        if (rows.isEmpty()) throw notFound();
        return rows.get(0);
    }

    public List<ImportItemView> listOwnedItems(UUID ownerAccountId, UUID batchId) {
        requireOwnedBatch(ownerAccountId, batchId);
        return jdbc.query(
                ITEM_SELECT + " WHERE i.batch_id = ? ORDER BY i.ordinal",
                this::mapItem, batchId);
    }

    public ImportStepView insertStep(UUID ownerAccountId, ImportStepCreate step) {
        int changed = jdbc.update("""
                INSERT INTO app.import_steps(
                    id, batch_id, item_id, step_key, ordinal, status, input_json)
                SELECT ?, b.id, ?, ?, ?, 'pending', ?::jsonb
                FROM app.import_batches b
                WHERE b.id = ? AND b.owner_account_id = ?
                  AND (?::uuid IS NULL OR EXISTS (
                    SELECT 1 FROM app.import_items i WHERE i.batch_id = b.id AND i.id = ?::uuid
                  ))
                """, step.id(), step.itemId(), step.stepKey(), step.ordinal(),
                writeJson(step.input()), step.batchId(), ownerAccountId, step.itemId(), step.itemId());
        if (changed == 0) throw notFound();
        return requireOwnedStep(ownerAccountId, step.batchId(), step.id());
    }

    public ImportStepView requireOwnedStep(UUID ownerAccountId, UUID batchId, UUID stepId) {
        List<ImportStepView> rows = jdbc.query(
                STEP_SELECT + " JOIN app.import_batches b ON b.id = s.batch_id"
                        + " WHERE s.id = ? AND s.batch_id = ? AND b.owner_account_id = ?",
                this::mapStep, stepId, batchId, ownerAccountId);
        if (rows.isEmpty()) throw notFound();
        return rows.get(0);
    }

    public List<ImportStepView> listOwnedSteps(UUID ownerAccountId, UUID batchId, UUID itemId) {
        requireOwnedBatch(ownerAccountId, batchId);
        if (itemId == null) {
            return jdbc.query(
                    STEP_SELECT + " WHERE s.batch_id = ? ORDER BY s.ordinal, s.created_at",
                    this::mapStep, batchId);
        }
        return jdbc.query(
                STEP_SELECT + " WHERE s.batch_id = ? AND s.item_id = ? ORDER BY s.ordinal, s.created_at",
                this::mapStep, batchId, itemId);
    }

    public ExternalResourceMappingView upsertMapping(UUID ownerAccountId,
                                                     ExternalResourceMappingCreate mapping) {
        requireOwnedBatch(ownerAccountId, mapping.batchId());
        int changed = jdbc.update("""
                INSERT INTO app.external_resource_map AS current(
                    id, owner_account_id, batch_id, item_id, producer_id, dataset_id,
                    external_resource_type, external_resource_id, internal_resource_type,
                    internal_resource_id, case_id, document_id, first_revision, last_revision,
                    source_sha256, source_version, metadata_json)
                SELECT ?, ?, b.id, i.id, ?, ?, ?, ?, ?, ?, c.id, d.id, ?, ?, ?, ?, ?::jsonb
                FROM app.import_batches b
                JOIN app.import_items i ON i.batch_id = b.id AND i.id = ?
                JOIN app.cases c ON c.id = ? AND c.owner_account_id = ?
                LEFT JOIN app.documents d ON d.id = ? AND d.case_id = c.id
                WHERE b.id = ? AND b.owner_account_id = ?
                  AND (?::text IS NULL OR d.id IS NOT NULL)
                ON CONFLICT (owner_account_id, producer_id, dataset_id,
                             external_resource_type, external_resource_id)
                DO UPDATE SET
                    batch_id = EXCLUDED.batch_id,
                    item_id = EXCLUDED.item_id,
                    internal_resource_type = EXCLUDED.internal_resource_type,
                    internal_resource_id = EXCLUDED.internal_resource_id,
                    case_id = EXCLUDED.case_id,
                    document_id = EXCLUDED.document_id,
                    last_revision = EXCLUDED.last_revision,
                    source_sha256 = EXCLUDED.source_sha256,
                    source_version = EXCLUDED.source_version,
                    active = TRUE,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = now()
                WHERE current.internal_resource_type = EXCLUDED.internal_resource_type
                  AND current.internal_resource_id = EXCLUDED.internal_resource_id
                  AND current.case_id = EXCLUDED.case_id
                  AND current.document_id IS NOT DISTINCT FROM EXCLUDED.document_id
                  AND current.source_sha256 IS NOT DISTINCT FROM EXCLUDED.source_sha256
                  AND current.source_version IS NOT DISTINCT FROM EXCLUDED.source_version
                """, mapping.id(), ownerAccountId, mapping.producerId(), mapping.datasetId(),
                mapping.externalResourceType(), mapping.externalResourceId(),
                mapping.internalResourceType(), mapping.internalResourceId(),
                mapping.revision(), mapping.revision(), mapping.sourceSha256(),
                mapping.sourceVersion(), writeJson(mapping.metadata()), mapping.itemId(),
                mapping.caseId(), ownerAccountId, mapping.documentId(), mapping.batchId(),
                ownerAccountId, mapping.documentId());
        if (changed == 0) {
            Long existing = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM app.external_resource_map
                    WHERE owner_account_id = ? AND producer_id = ? AND dataset_id = ?
                      AND external_resource_type = ? AND external_resource_id = ?
                    """, Long.class, ownerAccountId, mapping.producerId(), mapping.datasetId(),
                    mapping.externalResourceType(), mapping.externalResourceId());
            if (existing != null && existing > 0) {
                throw new ApiException(HttpStatus.CONFLICT, "IMPORT_MAPPING_CONFLICT",
                        "外部资源已映射到不同的内部资源");
            }
            throw notFound();
        }
        return requireMapping(ownerAccountId, mapping.producerId(), mapping.datasetId(),
                mapping.externalResourceType(), mapping.externalResourceId());
    }

    public ExternalResourceMappingView requireMapping(UUID ownerAccountId, String producerId,
                                                       String datasetId, String externalType,
                                                       String externalId) {
        return findMapping(ownerAccountId, producerId, datasetId, externalType, externalId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "IMPORT_MAPPING_NOT_FOUND",
                        "外部资源映射不存在或不可访问"));
    }

    public java.util.Optional<ExternalResourceMappingView> findMapping(
            UUID ownerAccountId, String producerId, String datasetId,
            String externalType, String externalId) {
        List<ExternalResourceMappingView> rows = jdbc.query(
                MAPPING_SELECT + " WHERE m.owner_account_id = ? AND m.producer_id = ?"
                        + " AND m.dataset_id = ? AND m.external_resource_type = ?"
                        + " AND m.external_resource_id = ?",
                this::mapMapping, ownerAccountId, producerId, datasetId, externalType, externalId);
        return rows.stream().findFirst();
    }

    public UUID claimApplyLease(UUID ownerAccountId, UUID batchId) {
        UUID leaseToken = UUID.randomUUID();
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'applying', started_at = COALESCE(started_at, now()), completed_at = NULL,
                    lease_token = ?, lease_expires_at = now() + interval '5 minutes', updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'approved'
                """, leaseToken, batchId, ownerAccountId);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
        return leaseToken;
    }

    public void casBatchStatus(UUID ownerAccountId, UUID batchId, String expected, String next) {
        if ("applying".equals(next)) {
            throw new IllegalArgumentException("applying status requires a lease token");
        }
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = ?,
                    started_at = CASE WHEN ? = 'validating' THEN COALESCE(started_at, now()) ELSE started_at END,
                    completed_at = NULL, lease_token = NULL, lease_expires_at = NULL, updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = ?
                """, next, next, batchId, ownerAccountId, expected);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void finishValidationSuccess(UUID ownerAccountId, UUID batchId,
                                        String schemaVersion, String packageId, String producerId,
                                        String datasetId, String revision, String digest) {
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'review_required', schema_version = ?, package_id = ?, producer_id = ?,
                    dataset_id = ?, revision = ?, package_digest = ?, error_json = NULL,
                    lease_expires_at = NULL, completed_at = NULL, updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'validating'
                """, schemaVersion, packageId, producerId, datasetId, revision, digest,
                batchId, ownerAccountId);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void finishValidationFailure(UUID ownerAccountId, UUID batchId,
                                        Map<String, Object> error) {
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'validation_failed', error_json = ?::jsonb,
                    completed_at = now(), lease_expires_at = NULL, updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'validating'
                """, writeJson(error), batchId, ownerAccountId);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void approveBatch(UUID ownerAccountId, UUID batchId, UUID actor) {
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'approved', approved_by = ?, approved_at = now(),
                    completed_at = NULL, lease_expires_at = NULL, updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'review_required'
                """, actor, batchId, ownerAccountId);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void finishBatch(UUID ownerAccountId, UUID batchId, UUID leaseToken, String status,
                            Map<String, Object> error) {
        if (!List.of("completed", "partially_completed", "failed").contains(status)) {
            throw statusConflict();
        }
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET status = ?, error_json = ?::jsonb, completed_at = now(),
                    lease_token = NULL, lease_expires_at = NULL, updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'applying' AND lease_token = ?
                """, status, writeJson(error), batchId, ownerAccountId, leaseToken);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void recoverExpiredApply(UUID ownerAccountId, UUID batchId) {
        int recovered = jdbc.update("""
                UPDATE app.import_batches
                SET status = 'approved', lease_token = NULL, lease_expires_at = NULL,
                    completed_at = NULL, updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'applying'
                  AND lease_expires_at < now()
                """, batchId, ownerAccountId);
        if (recovered == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
        jdbc.update("""
                UPDATE app.import_items
                SET status = 'approved', completed_at = NULL, updated_at = now()
                WHERE batch_id = ? AND owner_account_id = ? AND status = 'applying'
                """, batchId, ownerAccountId);
        jdbc.update("""
                UPDATE app.import_steps s
                SET status = 'pending', lease_token = NULL, lease_expires_at = NULL, started_at = NULL,
                    finished_at = NULL, error_json = NULL, updated_at = now()
                FROM app.import_batches b
                WHERE s.batch_id = ? AND b.id = s.batch_id AND b.owner_account_id = ?
                  AND s.status = 'running'
                """, batchId, ownerAccountId);
    }

    public void renewApplyLease(UUID ownerAccountId, UUID batchId, UUID leaseToken) {
        int changed = jdbc.update("""
                UPDATE app.import_batches
                SET lease_expires_at = now() + interval '5 minutes', updated_at = now()
                WHERE id = ? AND owner_account_id = ? AND status = 'applying' AND lease_token = ?
                """, batchId, ownerAccountId, leaseToken);
        if (changed == 0) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void renewStepLease(UUID ownerAccountId, UUID batchId, UUID stepId, UUID leaseToken) {
        int changed = jdbc.update("""
                UPDATE app.import_steps s
                SET lease_expires_at = now() + interval '5 minutes', updated_at = now()
                FROM app.import_batches b
                WHERE s.id = ? AND s.batch_id = ? AND b.id = s.batch_id
                  AND b.owner_account_id = ? AND b.status = 'applying' AND b.lease_token = ?
                  AND s.status = 'running' AND s.lease_token = ?
                """, stepId, batchId, ownerAccountId, leaseToken, leaseToken);
        if (changed == 0) {
            requireOwnedStep(ownerAccountId, batchId, stepId);
            throw statusConflict();
        }
    }

    public void audit(UUID ownerAccountId, UUID batchId, String action,
                      Map<String, Object> payload) {
        requireOwnedBatch(ownerAccountId, batchId);
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES (?, ?, 'import_batch', ?, ?::jsonb)
                """, "account:" + ownerAccountId, action, batchId.toString(), writeJson(payload));
    }

    public int deleteItemsForValidation(UUID ownerAccountId, UUID batchId) {
        ImportBatchView batch = requireOwnedBatch(ownerAccountId, batchId);
        if (!"validating".equals(batch.status())) {
            throw statusConflict();
        }
        return jdbc.update("""
                DELETE FROM app.import_items i
                WHERE i.batch_id = ? AND i.owner_account_id = ?
                  AND EXISTS (
                    SELECT 1 FROM app.import_batches b
                    WHERE b.id = i.batch_id AND b.owner_account_id = i.owner_account_id
                      AND b.status = 'validating'
                  )
                """, batchId, ownerAccountId);
    }

    public List<ImportItemView> listOwnedItems(UUID ownerAccountId, UUID batchId,
                                                int limit, int offset) {
        requireOwnedBatch(ownerAccountId, batchId);
        return jdbc.query(
                ITEM_SELECT + " WHERE i.batch_id = ? AND i.owner_account_id = ?"
                        + " ORDER BY i.ordinal LIMIT ? OFFSET ?",
                this::mapItem, batchId, ownerAccountId, limit, offset);
    }

    public long countOwnedItems(UUID ownerAccountId, UUID batchId) {
        requireOwnedBatch(ownerAccountId, batchId);
        Long total = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app.import_items
                WHERE batch_id = ? AND owner_account_id = ?
                """, Long.class, batchId, ownerAccountId);
        return total == null ? 0L : total;
    }

    public void setItemDiff(UUID ownerAccountId, UUID batchId, UUID itemId,
                            String status, Map<String, Object> diff, String caseId) {
        requireOwnedBatch(ownerAccountId, batchId);
        int changed = jdbc.update("""
                UPDATE app.import_items
                SET status = ?, diff_json = ?::jsonb, case_id = ?,
                    completed_at = CASE WHEN ? IN ('no_op', 'conflict', 'invalid', 'failed') THEN now() ELSE NULL END,
                    updated_at = now()
                WHERE id = ? AND batch_id = ? AND owner_account_id = ?
                """, status, writeJson(diff), caseId, status, itemId, batchId, ownerAccountId);
        if (changed == 0) throw notFound();
    }

    public int approveReviewableItems(UUID ownerAccountId, UUID batchId) {
        ImportBatchView batch = requireOwnedBatch(ownerAccountId, batchId);
        if (!"review_required".equals(batch.status())) {
            throw statusConflict();
        }
        return jdbc.update("""
                UPDATE app.import_items
                SET status = 'approved', updated_at = now()
                WHERE batch_id = ? AND owner_account_id = ? AND status = 'review_required'
                """, batchId, ownerAccountId);
    }

    public void setItemStatus(UUID ownerAccountId, UUID batchId, UUID itemId, UUID leaseToken,
                              String expected, String next, String caseId,
                              Map<String, Object> error) {
        requireOwnedBatch(ownerAccountId, batchId);
        int changed = jdbc.update("""
                UPDATE app.import_items i
                SET status = ?, case_id = ?, error_json = ?::jsonb,
                    started_at = CASE WHEN ? = 'applying' THEN COALESCE(i.started_at, now()) ELSE i.started_at END,
                    completed_at = CASE WHEN ? IN ('applied', 'failed', 'conflict', 'invalid', 'no_op') THEN now() ELSE NULL END,
                    updated_at = now()
                FROM app.import_batches b
                WHERE i.id = ? AND i.batch_id = ? AND i.owner_account_id = ? AND i.status = ?
                  AND b.id = i.batch_id AND b.status = 'applying' AND b.lease_token = ?
                """, next, caseId, writeJson(error), next, next,
                itemId, batchId, ownerAccountId, expected, leaseToken);
        if (changed == 0) {
            requireOwnedItem(ownerAccountId, batchId, itemId);
            throw statusConflict();
        }
    }

    public ImportStepView ensureStep(UUID ownerAccountId, ImportStepCreate step) {
        requireOwnedBatch(ownerAccountId, step.batchId());
        jdbc.update("""
                INSERT INTO app.import_steps(
                    id, batch_id, item_id, step_key, ordinal, status, input_json)
                SELECT ?, b.id, ?, ?, ?, 'pending', ?::jsonb
                FROM app.import_batches b
                WHERE b.id = ? AND b.owner_account_id = ?
                  AND (?::uuid IS NULL OR EXISTS (
                    SELECT 1 FROM app.import_items i WHERE i.batch_id = b.id AND i.id = ?::uuid
                  ))
                ON CONFLICT DO NOTHING
                """, step.id(), step.itemId(), step.stepKey(), step.ordinal(),
                writeJson(step.input()), step.batchId(), ownerAccountId,
                step.itemId(), step.itemId());
        List<ImportStepView> rows;
        if (step.itemId() == null) {
            rows = jdbc.query(
                    STEP_SELECT + " JOIN app.import_batches b ON b.id = s.batch_id"
                            + " WHERE s.batch_id = ? AND s.item_id IS NULL AND s.step_key = ?"
                            + " AND b.owner_account_id = ?",
                    this::mapStep, step.batchId(), step.stepKey(), ownerAccountId);
        } else {
            rows = jdbc.query(
                    STEP_SELECT + " JOIN app.import_batches b ON b.id = s.batch_id"
                            + " WHERE s.batch_id = ? AND s.item_id = ? AND s.step_key = ?"
                            + " AND b.owner_account_id = ?",
                    this::mapStep, step.batchId(), step.itemId(), step.stepKey(), ownerAccountId);
        }
        if (rows.isEmpty()) throw notFound();
        return rows.get(0);
    }

    public void lockApplyLease(UUID ownerAccountId, UUID batchId, UUID leaseToken) {
        List<UUID> rows = jdbc.query("""
                SELECT id FROM app.import_batches
                WHERE id = ? AND owner_account_id = ? AND status = 'applying' AND lease_token = ?
                FOR UPDATE
                """, (rs, ignored) -> rs.getObject("id", UUID.class), batchId, ownerAccountId, leaseToken);
        if (rows.isEmpty()) {
            requireOwnedBatch(ownerAccountId, batchId);
            throw statusConflict();
        }
    }

    public void markStepFailure(UUID ownerAccountId, UUID batchId, UUID stepId, UUID leaseToken,
                                Map<String, Object> error) {
        int changed = jdbc.update("""
                UPDATE app.import_steps s
                SET status = 'failed', error_json = ?::jsonb, finished_at = now(),
                    lease_token = NULL, lease_expires_at = NULL, updated_at = now()
                FROM app.import_batches b
                WHERE s.id = ? AND s.batch_id = ? AND b.id = s.batch_id
                  AND b.owner_account_id = ? AND b.status = 'applying' AND b.lease_token = ?
                  AND s.status IN ('pending', 'failed')
                """, writeJson(error), stepId, batchId, ownerAccountId, leaseToken);
        if (changed == 0) {
            requireOwnedStep(ownerAccountId, batchId, stepId);
            throw statusConflict();
        }
    }

    public void claimStep(UUID ownerAccountId, UUID batchId, UUID stepId, UUID leaseToken) {
        requireOwnedBatch(ownerAccountId, batchId);
        int changed = jdbc.update("""
                UPDATE app.import_steps s
                SET status = 'running', attempt = attempt + 1, started_at = now(),
                    finished_at = NULL, output_json = NULL, error_json = NULL,
                    lease_token = ?, lease_expires_at = now() + interval '5 minutes', updated_at = now()
                FROM app.import_batches b
                WHERE s.id = ? AND s.batch_id = ? AND b.id = s.batch_id
                  AND b.owner_account_id = ? AND b.status = 'applying' AND b.lease_token = ?
                  AND s.status IN ('pending', 'failed')
                """, leaseToken, stepId, batchId, ownerAccountId, leaseToken);
        if (changed == 0) {
            requireOwnedStep(ownerAccountId, batchId, stepId);
            throw statusConflict();
        }
    }

    public void completeStep(UUID ownerAccountId, UUID batchId, UUID stepId, UUID leaseToken,
                             Map<String, Object> output) {
        requireOwnedBatch(ownerAccountId, batchId);
        int changed = jdbc.update("""
                UPDATE app.import_steps s
                SET status = 'completed', output_json = ?::jsonb, error_json = NULL,
                    finished_at = now(), lease_token = NULL, lease_expires_at = NULL, updated_at = now()
                FROM app.import_batches b
                WHERE s.id = ? AND s.batch_id = ? AND b.id = s.batch_id
                  AND b.owner_account_id = ? AND b.status = 'applying' AND b.lease_token = ?
                  AND s.status = 'running' AND s.lease_token = ?
                """, writeJson(output), stepId, batchId, ownerAccountId, leaseToken, leaseToken);
        if (changed == 0) {
            requireOwnedStep(ownerAccountId, batchId, stepId);
            throw statusConflict();
        }
    }

    public void failStep(UUID ownerAccountId, UUID batchId, UUID stepId, UUID leaseToken,
                         Map<String, Object> error) {
        requireOwnedBatch(ownerAccountId, batchId);
        int changed = jdbc.update("""
                UPDATE app.import_steps s
                SET status = 'failed', error_json = ?::jsonb, finished_at = now(),
                    lease_token = NULL, lease_expires_at = NULL, updated_at = now()
                FROM app.import_batches b
                WHERE s.id = ? AND s.batch_id = ? AND b.id = s.batch_id
                  AND b.owner_account_id = ? AND b.status = 'applying' AND b.lease_token = ?
                  AND s.status = 'running' AND s.lease_token = ?
                """, writeJson(error), stepId, batchId, ownerAccountId, leaseToken, leaseToken);
        if (changed == 0) {
            requireOwnedStep(ownerAccountId, batchId, stepId);
            throw statusConflict();
        }
    }

    public int resetFailedSteps(UUID ownerAccountId, UUID batchId) {
        requireOwnedBatch(ownerAccountId, batchId);
        return jdbc.update("""
                UPDATE app.import_steps s
                SET status = 'pending', started_at = NULL, finished_at = NULL,
                    lease_token = NULL, lease_expires_at = NULL, output_json = NULL, error_json = NULL, updated_at = now()
                FROM app.import_batches b
                WHERE s.batch_id = ? AND b.id = s.batch_id AND b.owner_account_id = ?
                  AND s.status = 'failed'
                """, batchId, ownerAccountId);
    }

    public int resetFailedItems(UUID ownerAccountId, UUID batchId) {
        requireOwnedBatch(ownerAccountId, batchId);
        return jdbc.update("""
                UPDATE app.import_items
                SET status = 'approved', error_json = NULL, completed_at = NULL, updated_at = now()
                WHERE batch_id = ? AND owner_account_id = ? AND status = 'failed'
                """, batchId, ownerAccountId);
    }

    public void auditBatchCreated(UUID ownerAccountId, ImportBatchView batch) {
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES (?, 'import.batch.created', 'import_batch', ?,
                        jsonb_build_object('filename', ?, 'sha256', ?, 'sizeBytes', ?))
                """, "account:" + ownerAccountId, batch.id().toString(),
                batch.originalFilename(), batch.rawSha256(), batch.sizeBytes());
    }

    private ImportBatchView mapBatch(ResultSet rs, int ignored) throws SQLException {
        return new ImportBatchView(
                rs.getObject("id", UUID.class),
                rs.getObject("owner_account_id", UUID.class),
                rs.getString("schema_version"),
                rs.getString("package_id"),
                rs.getString("producer_id"),
                rs.getString("dataset_id"),
                rs.getString("revision"),
                rs.getString("package_digest"),
                rs.getString("original_filename"),
                rs.getString("content_type"),
                rs.getLong("size_bytes"),
                rs.getString("raw_sha256"),
                rs.getString("storage_key"),
                rs.getString("status"),
                readMap(rs.getString("metadata_json")),
                readNullableMap(rs.getString("error_json")),
                rs.getObject("approved_by", UUID.class),
                rs.getObject("approved_at", OffsetDateTime.class),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("updated_at", OffsetDateTime.class),
                rs.getObject("started_at", OffsetDateTime.class),
                rs.getObject("completed_at", OffsetDateTime.class));
    }

    private ImportItemView mapItem(ResultSet rs, int ignored) throws SQLException {
        return new ImportItemView(
                rs.getObject("id", UUID.class),
                rs.getObject("batch_id", UUID.class),
                rs.getInt("ordinal"),
                rs.getString("item_id"),
                rs.getString("external_case_id"),
                rs.getString("payload_path"),
                rs.getString("payload_sha256"),
                rs.getString("status"),
                rs.getString("case_id"),
                readNullableMap(rs.getString("diff_json")),
                readMap(rs.getString("metadata_json")),
                readNullableMap(rs.getString("error_json")),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("updated_at", OffsetDateTime.class),
                rs.getObject("started_at", OffsetDateTime.class),
                rs.getObject("completed_at", OffsetDateTime.class));
    }

    private ImportStepView mapStep(ResultSet rs, int ignored) throws SQLException {
        return new ImportStepView(
                rs.getObject("id", UUID.class),
                rs.getObject("batch_id", UUID.class),
                rs.getObject("item_id", UUID.class),
                rs.getString("step_key"),
                rs.getInt("ordinal"),
                rs.getInt("attempt"),
                rs.getString("status"),
                readNullableMap(rs.getString("input_json")),
                readNullableMap(rs.getString("output_json")),
                readNullableMap(rs.getString("error_json")),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("updated_at", OffsetDateTime.class),
                rs.getObject("started_at", OffsetDateTime.class),
                rs.getObject("finished_at", OffsetDateTime.class));
    }

    private ExternalResourceMappingView mapMapping(ResultSet rs, int ignored) throws SQLException {
        return new ExternalResourceMappingView(
                rs.getObject("id", UUID.class),
                rs.getObject("owner_account_id", UUID.class),
                rs.getObject("batch_id", UUID.class),
                rs.getObject("item_id", UUID.class),
                rs.getString("producer_id"),
                rs.getString("dataset_id"),
                rs.getString("external_resource_type"),
                rs.getString("external_resource_id"),
                rs.getString("internal_resource_type"),
                rs.getString("internal_resource_id"),
                rs.getString("case_id"),
                rs.getString("document_id"),
                rs.getString("first_revision"),
                rs.getString("last_revision"),
                rs.getString("source_sha256"),
                rs.getString("source_version"),
                rs.getBoolean("active"),
                readMap(rs.getString("metadata_json")),
                rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("updated_at", OffsetDateTime.class));
    }

    private String writeJson(Map<String, Object> value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("unable to serialize import metadata", ex);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readMap(String value) {
        if (value == null || value.isBlank()) return Map.of();
        try {
            return objectMapper.readValue(value, Map.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("invalid import JSON", ex);
        }
    }

    private Map<String, Object> readNullableMap(String value) {
        return value == null ? null : readMap(value);
    }

    private static ApiException statusConflict() {
        return new ApiException(HttpStatus.CONFLICT, "IMPORT_STATUS_CONFLICT", "导入状态已变更，请刷新后重试");
    }

    private static ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "IMPORT_BATCH_NOT_FOUND", "导入批次不存在或不可访问");
    }
}
