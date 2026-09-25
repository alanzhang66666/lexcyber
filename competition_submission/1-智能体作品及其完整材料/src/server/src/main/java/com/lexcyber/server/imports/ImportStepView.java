package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record ImportStepView(
        UUID id,
        UUID batchId,
        UUID itemId,
        String stepKey,
        int ordinal,
        int attempt,
        String status,
        Map<String, Object> input,
        Map<String, Object> output,
        Map<String, Object> error,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime startedAt,
        OffsetDateTime finishedAt) {
}
