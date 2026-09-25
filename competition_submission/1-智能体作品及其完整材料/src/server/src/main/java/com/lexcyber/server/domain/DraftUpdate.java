package com.lexcyber.server.domain;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record DraftUpdate(
        @NotNull String body,
        @NotNull @Min(1) Integer version,
        String templateVersion,
        String sourceVersion) {
    public DraftUpdate(String body, Integer version) {
        this(body, version, null, null);
    }
}
