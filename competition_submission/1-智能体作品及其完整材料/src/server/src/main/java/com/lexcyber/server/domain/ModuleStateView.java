package com.lexcyber.server.domain;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record ModuleStateView(
        String caseId,
        String module,
        String schemaVersion,
        String applicability,
        String status,
        int version,
        Map<String, Object> content,
        String sourceVersion,
        OffsetDateTime factsUpdatedAt,
        boolean factsStale,
        UUID updatedBy,
        OffsetDateTime updatedAt,
        OffsetDateTime confirmedAt) {
}
