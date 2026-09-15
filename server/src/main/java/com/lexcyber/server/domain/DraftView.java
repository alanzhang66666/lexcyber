package com.lexcyber.server.domain;

import java.time.OffsetDateTime;
import java.util.UUID;

public record DraftView(
        String id,
        String caseId,
        String draftType,
        String body,
        int version,
        UUID updatedBy,
        OffsetDateTime updatedAt,
        String templateVersion,
        String sourceVersion) {
    public DraftView(String id, String caseId, String draftType, String body, int version,
                     UUID updatedBy, OffsetDateTime updatedAt) {
        this(id, caseId, draftType, body, version, updatedBy, updatedAt, null, null);
    }
}
