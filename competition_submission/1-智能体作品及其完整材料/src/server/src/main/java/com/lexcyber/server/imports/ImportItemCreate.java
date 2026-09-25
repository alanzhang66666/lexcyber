package com.lexcyber.server.imports;

import java.util.Map;
import java.util.UUID;

public record ImportItemCreate(
        UUID id,
        UUID batchId,
        int ordinal,
        String itemId,
        String externalCaseId,
        String payloadPath,
        String payloadSha256,
        Map<String, Object> metadata) {

    public ImportItemCreate {
        metadata = ImportJson.copyMap(metadata);
    }
}
