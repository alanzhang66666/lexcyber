package com.lexcyber.server.domain;

import java.time.OffsetDateTime;
import java.util.UUID;

public record TaskView(
        UUID id,
        UUID requestId,
        UUID executionId,
        String caseId,
        String status,
        String currentStage,
        ResultRef result,
        String error,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {
}
