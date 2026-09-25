package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record DraftCreate(
        @NotBlank @Size(max = 64) String draftType,
        String body,
        String templateVersion,
        String sourceVersion) {
    public DraftCreate(String draftType, String body) {
        this(draftType, body, null, null);
    }
}
