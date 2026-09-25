package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record ExternalResourceMappingView(
        UUID id,
        UUID ownerAccountId,
        UUID batchId,
        UUID itemId,
        String producerId,
        String datasetId,
        String externalResourceType,
        String externalResourceId,
        String internalResourceType,
        String internalResourceId,
        String caseId,
        String documentId,
        String firstRevision,
        String lastRevision,
        String sourceSha256,
        String sourceVersion,
        boolean active,
        Map<String, Object> metadata,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {
}
