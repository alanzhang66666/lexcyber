package com.lexcyber.server.settings;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

/** Writable model-access fields. The API key is write-only: null keeps the stored key and an empty value clears it. */
public record ModelAccessConfigUpdate(
        @NotBlank @Pattern(regexp = "^(stub|openai)$") String provider,
        @NotBlank @Size(max = 200) String modelName,
        @NotBlank @Pattern(regexp = "^https?://") @Size(max = 500) String apiBaseUrl,
        @Size(max = 500) String apiKey,
        @NotNull @Positive @DecimalMax("600") Double timeoutSeconds) {
}
