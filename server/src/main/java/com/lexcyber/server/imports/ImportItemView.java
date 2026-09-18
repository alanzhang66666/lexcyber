package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record ImportItemView(
        UUID id,
        UUID batchId,
        int ordinal,
        String itemId,
        String externalCaseId,
        String payloadPath,
        String payloadSha256,
        String status,
        String caseId,
        Map<String, Object> diff,
        Map<String, Object> metadata,
        Map<String, Object> error,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime startedAt,
        OffsetDateTime completedAt) {
}
