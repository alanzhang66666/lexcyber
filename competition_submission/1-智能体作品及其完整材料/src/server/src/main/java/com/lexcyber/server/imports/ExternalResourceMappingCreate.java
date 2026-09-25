package com.lexcyber.server.imports;

import java.util.Map;
import java.util.UUID;

public record ExternalResourceMappingCreate(
        UUID id,
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
        String revision,
        String sourceSha256,
        String sourceVersion,
        Map<String, Object> metadata) {

    public ExternalResourceMappingCreate {
        metadata = ImportJson.copyMap(metadata);
    }
}
