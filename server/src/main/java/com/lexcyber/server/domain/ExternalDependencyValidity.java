package com.lexcyber.server.domain;

import java.util.List;

/** Immutable dependency tuple exchanged with the Engine registry. */
public record ExternalDependencyValidity(String kind, String key, String version) {
    public ExternalDependencyValidity {
        if (kind == null || kind.isBlank() || key == null || key.isBlank()
                || version == null || version.isBlank()) {
            throw new IllegalArgumentException("external dependency tuples require kind, key and version");
        }
    }

    public record InvalidDependency(String kind, String key, String version, String reason) {}

    public record Verification(boolean valid, List<InvalidDependency> invalidDependencies) {
        public Verification {
            if (invalidDependencies == null) {
                throw new IllegalArgumentException("registry response must include invalidDependencies");
            }
            invalidDependencies = List.copyOf(invalidDependencies);
            if (valid && !invalidDependencies.isEmpty()) {
                throw new IllegalArgumentException("a valid registry response cannot contain invalid dependencies");
            }
        }
    }
}
