package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record ImportBatchView(
        UUID id,
        UUID ownerAccountId,
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
        String storageKey,
        String status,
        Map<String, Object> metadata,
        Map<String, Object> error,
        UUID approvedBy,
        OffsetDateTime approvedAt,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime startedAt,
        OffsetDateTime completedAt) {
}
