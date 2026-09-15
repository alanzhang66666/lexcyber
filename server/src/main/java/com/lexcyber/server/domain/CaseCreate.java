package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import java.util.Map;

public record CaseCreate(
        @NotBlank @Size(max = 200) String title,
        @Size(max = 32) String jurisdiction,
        LocalDate asOfDate,
        Map<String, Object> metadata) {
}
