package com.lexcyber.server.domain;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

public record ModuleStateUpdate(
        String applicability,
        Map<String, Object> content,
        String sourceVersion,
        @NotNull @Min(0) Integer version) {
}
