package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record ImportBatchResponse(
        UUID id,
        String status,
        String schemaVersion,
        String packageId,
        String producerId,
        String datasetId,
        String revision,
        String packageDigest,
        String originalFilename,
        String contentType,
        long sizeBytes,
        String rawSha256,
        Map<String, Object> error,
        OffsetDateTime approvedAt,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime startedAt,
        OffsetDateTime completedAt) {

    public static ImportBatchResponse from(ImportBatchView value) {
        return new ImportBatchResponse(
                value.id(), value.status(), value.schemaVersion(), value.packageId(),
                value.producerId(), value.datasetId(), value.revision(), value.packageDigest(),
                value.originalFilename(), value.contentType(), value.sizeBytes(), value.rawSha256(),
                value.error(), value.approvedAt(), value.createdAt(), value.updatedAt(),
                value.startedAt(), value.completedAt());
    }
}
