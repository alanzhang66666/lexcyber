package com.lexcyber.server.imports;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

final class ImportJson {
    private ImportJson() {
    }

    static Map<String, Object> copyMap(Map<String, Object> value) {
        if (value == null || value.isEmpty()) return Map.of();
        return Collections.unmodifiableMap(new LinkedHashMap<>(value));
    }
}
