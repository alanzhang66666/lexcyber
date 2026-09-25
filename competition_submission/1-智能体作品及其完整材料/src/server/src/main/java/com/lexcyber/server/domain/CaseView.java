package com.lexcyber.server.domain;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Map;

public record CaseView(
        String id,
        String title,
        String jurisdiction,
        LocalDate asOfDate,
        Map<String, Object> metadata,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {
}
