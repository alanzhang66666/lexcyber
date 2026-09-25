package com.lexcyber.server.settings;

import java.time.OffsetDateTime;

/** Public model-access configuration view; API key material is never a field here. */
public record ModelAccessConfigView(
        String provider,
        String modelName,
        String apiBaseUrl,
        Double timeoutSeconds,
        boolean apiKeyConfigured,
        String apiKeyMask,
        String source,
        String updatedBy,
        OffsetDateTime updatedAt) {
    public static final String API_KEY_MASK = "********";
}
