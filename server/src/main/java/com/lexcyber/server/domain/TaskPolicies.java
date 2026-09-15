package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;

/** Validates public taskType values without guessing from query text. */
public final class TaskPolicies {
    public static final String DOCUMENT_PARSE = "document.parse";
    public static final String MODEL_PROBE = "model.probe";
    public static final String SENTENCING_CALCULATE = "sentencing.calculate";
    private static final Set<String> KNOWN = Set.of(DOCUMENT_PARSE, MODEL_PROBE, SENTENCING_CALCULATE);

    private TaskPolicies() {
    }

    public static String taskType(Map<String, Object> metadata) {
        if (metadata == null) return null;
        Object value = metadata.get("taskType");
        if (value == null) return null;
        String type = String.valueOf(value).trim();
        return type.isBlank() ? null : type;
    }

    public static void requireSupported(Map<String, Object> metadata, boolean sentencingEnabled) {
        String type = taskType(metadata);
        if (type == null) return;
        if (!KNOWN.contains(type)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_TASK_TYPE", "unsupported taskType");
        }
        if (SENTENCING_CALCULATE.equals(type) && !sentencingEnabled) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "SENTENCING_UNAVAILABLE", "量刑计算尚未接通");
        }
    }

    public static boolean requiresAuth(String type) {
        return type != null && KNOWN.contains(type);
    }
}
