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
}
