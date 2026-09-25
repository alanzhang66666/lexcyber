package com.lexcyber.server.engine;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class EngineDispatcherTest {
    @Test
    void modelProbeUsesDedicatedEngineStage() {
        String stage = stageFor(Map.of("taskType", "model.probe"));

        assertEquals("model_probe", stage);
        assertNotEquals("delegated", stage);
    }

    @Test
    void otherTaskTypesNeverUseModelProbeStage() {
        for (String taskType : List.of("document.parse", "sentencing.calculate", "unknown.job")) {
            assertNotEquals("model_probe", stageFor(Map.of("taskType", taskType)), taskType);
        }
        assertNotEquals("model_probe", stageFor(null), "missing taskType");
    }

    private static String stageFor(Map<String, Object> metadata) {
        try {
            Method route = EngineDispatcher.class.getDeclaredMethod("stageFor", ExecutionRequest.class);
            route.setAccessible(true);
            return (String) route.invoke(null, requestWith(metadata));
        } catch (ReflectiveOperationException failure) {
            throw new AssertionError("Unable to invoke EngineDispatcher routing behavior", failure);
        }
    }

    private static ExecutionRequest requestWith(Map<String, Object> metadata) {
        return new ExecutionRequest(
                UUID.randomUUID(),
                UUID.randomUUID(),
                UUID.randomUUID(),
                UUID.randomUUID(),
                1,
                "model.probe",
                "test query",
                null,
                null,
                metadata,
                null,
                "0.8.0",
                null,
                null);
    }
}
