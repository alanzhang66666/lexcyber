package com.lexcyber.server.domain;

public record FactItem(
        String id,
        String key,
        String value,
        String locator,
        String sourceDocumentId,
        String verificationStatus,
        String sourceVersion) {
    public FactItem(String id, String key, String value, String locator, String sourceDocumentId) {
        this(id, key, value, locator, sourceDocumentId, null, null);
    }
}
