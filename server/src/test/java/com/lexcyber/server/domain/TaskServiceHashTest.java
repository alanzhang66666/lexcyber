package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * input_hash 必须与 Engine 端 canonical_input_hash 逐字节一致——
 * BigDecimal 带 scale（numeric 列读出）曾导致 409 循环。
 */
class TaskServiceHashTest {

    @Test
    void bigDecimalScaleDoesNotChangeInputHash() throws Exception {
        TaskService service = new TaskService(null, new ObjectMapper());
        Map<String, Object> withScale = new LinkedHashMap<>();
        withScale.put("amounts", List.of(Map.of("value", new BigDecimal("250000.0000"))));
        Map<String, Object> plain = Map.of("amounts", List.of(Map.of("value", 250000.0)));

        String a = hash(service, withScale);
        String b = hash(service, plain);
        assertEquals(b, a, "BigDecimal scale must normalize to double before hashing");
    }

    private static String hash(TaskService service, Map<String, Object> metadata) throws Exception {
        Method normalize = TaskService.class.getDeclaredMethod("normalizeJson", Map.class);
        normalize.setAccessible(true);
        @SuppressWarnings("unchecked")
        Map<String, Object> normalized = (Map<String, Object>) normalize.invoke(null, metadata);
        Method hashInput = TaskService.class.getDeclaredMethod(
                "hashInput", String.class, String.class, String.class, Map.class);
        hashInput.setAccessible(true);
        return (String) hashInput.invoke(service, "q", "case", null, normalized);
    }
}
