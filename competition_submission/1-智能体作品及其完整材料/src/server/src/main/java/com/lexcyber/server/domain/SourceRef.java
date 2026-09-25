package com.lexcyber.server.domain;

public record SourceRef(String sourceId, String locator, String jurisdiction, String version, String effectiveFrom, String effectiveTo) {
}
