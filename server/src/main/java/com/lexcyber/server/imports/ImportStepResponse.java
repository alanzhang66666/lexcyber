package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.Map;

public record ImportStepResponse(
        String stepKey,
        int attempt,
        String status,
        Map<String, Object> error,
        OffsetDateTime startedAt,
        OffsetDateTime finishedAt) {

    public static ImportStepResponse from(ImportStepView value) {
        return new ImportStepResponse(
                value.stepKey(), value.attempt(), value.status(), value.error(),
                value.startedAt(), value.finishedAt());
    }
}
