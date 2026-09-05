package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.Map;

public record TaskCreate(
        @NotBlank @Size(max = 20_000) String query,
        String caseId,
        String sessionId,
        Map<String, Object> metadata) {
}
