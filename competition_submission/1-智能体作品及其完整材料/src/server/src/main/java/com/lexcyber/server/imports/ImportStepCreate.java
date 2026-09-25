package com.lexcyber.server.imports;

import java.util.Map;
import java.util.UUID;

public record ImportStepCreate(
        UUID id,
        UUID batchId,
        UUID itemId,
        String stepKey,
        int ordinal,
        Map<String, Object> input) {

    public ImportStepCreate {
        input = ImportJson.copyMap(input);
    }
}
