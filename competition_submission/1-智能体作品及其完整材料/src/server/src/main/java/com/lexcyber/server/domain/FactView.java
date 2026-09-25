package com.lexcyber.server.domain;

import java.time.OffsetDateTime;
import java.util.List;

public record FactView(
        String caseId,
        String schemaVersion,
        String status,
        List<FactItem> items,
        OffsetDateTime updatedAt,
        OffsetDateTime confirmedAt) {
}
