package com.lexcyber.server.domain;

import java.time.OffsetDateTime;
import java.util.UUID;

public record DocumentView(
        String id,
        String caseId,
        String filename,
        String contentType,
        long size,
        String role,
        String parseStatus,
        UUID parseTaskId,
        OffsetDateTime createdAt) {
}
