package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.Set;
import org.springframework.http.HttpStatus;

/** Shared enums for case-level compliance/conviction shells. */
public final class ModulePolicies {
    public static final String COMPLIANCE = "compliance";
    public static final String CONVICTION = "conviction";
    public static final String SCHEMA_VERSION = "case.module.v1";
    public static final Set<String> MODULES = Set.of(COMPLIANCE, CONVICTION);
    public static final Set<String> APPLICABILITY =
            Set.of("unknown", "not_applicable", "limited_context", "applicable");
    public static final Set<String> VERIFICATION =
            Set.of("candidate", "baseline_asserted", "confirmed", "rejected", "conflicted");
    public static final Set<String> REVIEW_MODULES =
            Set.of("compliance", "conviction", "draft", "parse", "sentencing", "task");

    private ModulePolicies() {
    }

    public static String requireModule(String module) {
        String value = module == null ? "" : module.trim();
        if (!MODULES.contains(value)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "module must be compliance or conviction");
        }
        return value;
    }

    public static String requireApplicability(String applicability) {
        if (applicability == null || applicability.isBlank()) {
            return "unknown";
        }
        String value = applicability.trim();
        if (!APPLICABILITY.contains(value)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "unsupported applicability");
        }
        return value;
    }

    public static String requireReviewModule(String module) {
        if (module == null || module.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "module is required");
        }
        String value = module.trim();
        if (!REVIEW_MODULES.contains(value)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "unsupported review module");
        }
        return value;
    }
}
