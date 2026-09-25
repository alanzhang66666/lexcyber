package com.lexcyber.server.domain;

public record SourceSearchHit(
        String sourceId,
        String locator,
        String title,
        String quote,
        String version,
        String jurisdiction) {
}
