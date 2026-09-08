package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;

public record SourceSearchRequest(
        @NotBlank @Size(max = 4000) String query,
        @Size(max = 32) String jurisdiction,
        LocalDate asOfDate,
        Integer topK) {
}
