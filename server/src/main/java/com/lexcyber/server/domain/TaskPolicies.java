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
    public static final String COMPLIANCE_ANALYZE = "compliance.analyze";
    public static final String CONVICTION_ANALYZE = "conviction.analyze";
    public static final String DRAFT_RENDER = "draft.render";
    private static final Set<String> KNOWN = Set.of(
            DOCUMENT_PARSE, MODEL_PROBE, SENTENCING_CALCULATE, COMPLIANCE_ANALYZE,
            CONVICTION_ANALYZE, DRAFT_RENDER);

    private TaskPolicies() {
    }

    public static String taskType(Map<String, Object> metadata) {
        if (metadata == null) return null;
        Object value = metadata.get("taskType");
        if (value == null) return null;
        String type = String.valueOf(value).trim();
        return type.isBlank() ? null : type;
    }

    /** 仅校验 taskType 已知，不做可用性门闩（/v2 内部派发用，能力门闩前置）。 */
    public static void requireKnown(Map<String, Object> metadata) {
        String type = taskType(metadata);
        if (type != null && !KNOWN.contains(type)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_TASK_TYPE", "unsupported taskType");
        }
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
        if (COMPLIANCE_ANALYZE.equals(type)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "COMPLIANCE_UNAVAILABLE", "合规分析尚未接通");
        }
        if (CONVICTION_ANALYZE.equals(type)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "CONVICTION_UNAVAILABLE", "定罪分析尚未接通");
        }
        if (DRAFT_RENDER.equals(type)) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "DRAFT_RENDER_UNAVAILABLE", "文书渲染尚未接通");
        }
    }

    public static boolean requiresAuth(String type) {
        return type != null && KNOWN.contains(type);
    }
}
