package com.lexcyber.server.domain;

public record FactItem(
        String id,
        String key,
        String value,
        String locator,
        String sourceDocumentId) {
}
