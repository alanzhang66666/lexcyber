package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class TaskPoliciesTest {
    @Test
    void missingTaskTypeStaysCompatible() {
        TaskPolicies.requireSupported(null, false);
        TaskPolicies.requireSupported(Map.of("source", "ci"), false);
    }

    @Test
    void unknownTaskTypeIs400() {
        ApiException error = assertThrows(ApiException.class,
                () -> TaskPolicies.requireSupported(Map.of("taskType", "unknown.job"), false));
        assertEquals(HttpStatus.BAD_REQUEST, error.status());
        assertEquals("INVALID_TASK_TYPE", error.code());
    }

    @Test
    void sentencingIs501WhenDisabled() {
        ApiException error = assertThrows(ApiException.class,
                () -> TaskPolicies.requireSupported(Map.of("taskType", "sentencing.calculate"), false));
        assertEquals(HttpStatus.NOT_IMPLEMENTED, error.status());
        assertEquals("SENTENCING_UNAVAILABLE", error.code());
    }

    @Test
    void knownTypesAreAccepted() {
        TaskPolicies.requireSupported(Map.of("taskType", "document.parse"), false);
        TaskPolicies.requireSupported(Map.of("taskType", "model.probe"), false);
        TaskPolicies.requireSupported(Map.of("taskType", "sentencing.calculate"), true);
    }

    @Test
    void analyzeTaskTypesAreAlways501() {
        ApiException compliance = assertThrows(ApiException.class,
                () -> TaskPolicies.requireSupported(Map.of("taskType", "compliance.analyze"), true));
        assertEquals(HttpStatus.NOT_IMPLEMENTED, compliance.status());
        assertEquals("COMPLIANCE_UNAVAILABLE", compliance.code());
        ApiException conviction = assertThrows(ApiException.class,
                () -> TaskPolicies.requireSupported(Map.of("taskType", "conviction.analyze"), true));
        assertEquals(HttpStatus.NOT_IMPLEMENTED, conviction.status());
        assertEquals("CONVICTION_UNAVAILABLE", conviction.code());
    }

    @Test
    void reservedTaskTypesRequireAuth() {
        assertEquals(true, TaskPolicies.requiresAuth("document.parse"));
        assertEquals(true, TaskPolicies.requiresAuth("model.probe"));
        assertEquals(true, TaskPolicies.requiresAuth("sentencing.calculate"));
        assertEquals(true, TaskPolicies.requiresAuth("compliance.analyze"));
        assertEquals(true, TaskPolicies.requiresAuth("conviction.analyze"));
        assertEquals(false, TaskPolicies.requiresAuth(null));
        assertEquals(false, TaskPolicies.requiresAuth(""));
    }
}
