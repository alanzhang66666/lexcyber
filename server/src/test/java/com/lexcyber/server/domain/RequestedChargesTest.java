package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class RequestedChargesTest {
    @Test
    void freezesExactExplicitInputWithoutInferringAKey() {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("requestedCharge", " 未覆盖罪名 ");
        row.put("chargeKey", null);
        List<Map<String, Object>> input = new ArrayList<>(List.of(row));
        List<Map<String, Object>> frozen = RequestedCharges.freeze("conviction", Map.of("requestedCharges", input));
        row.put("requestedCharge", "changed");
        input.clear();
        assertEquals(" 未覆盖罪名 ", frozen.get(0).get("requestedCharge"));
        assertEquals(null, frozen.get(0).get("chargeKey"));
        assertThrows(UnsupportedOperationException.class, () -> frozen.get(0).put("chargeKey", "guessed"));
    }

    @Test
    void emptyRequestsKeepOldCallersCompatible() {
        assertEquals(List.of(), RequestedCharges.freeze("conviction", null));
        assertEquals(List.of(), RequestedCharges.freeze("conviction", Map.of()));
        assertEquals(List.of(), RequestedCharges.freeze("compliance", Map.of("requestedCharges", List.of())));
        Map<String, Object> keyed = Map.of("requestedCharge", "same", "chargeKey", " raw.key ");
        Map<String, Object> unkeyed = Map.of("requestedCharge", "same");
        for (List<Map<String, Object>> order : List.of(List.of(keyed, unkeyed), List.of(unkeyed, keyed))) {
            assertEquals(order, RequestedCharges.freeze("conviction", Map.of("requestedCharges", order)));
        }
    }

    @Test
    void rejectsInvalidTypesUnknownFieldsDuplicatesAndOtherModules() {
        List<Map<String, Object>> invalidBodies = List.of(
                Map.of("unexpected", List.of()),
                Map.of("requestedCharges", "crime"),
                Map.of("requestedCharges", List.of("crime")),
                Map.of("requestedCharges", List.of(Map.of("chargeKey", "crime"))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", 1))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", " "))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", "x", "chargeKey", true))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", "x", "extra", "x"))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", "x"), Map.of("requestedCharge", "x"))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", "a", "chargeKey", "same"),
                        Map.of("requestedCharge", "b", "chargeKey", "same"))),
                Map.of("requestedCharges", java.util.Collections.nCopies(33, Map.of("requestedCharge", "x"))),
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", "x".repeat(201)))));
        for (Map<String, Object> body : invalidBodies) {
            ApiException error = assertThrows(ApiException.class, () -> RequestedCharges.freeze("conviction", body));
            assertEquals("INVALID_REQUESTED_CHARGES", error.code());
        }
        Map<String, Object> explicitNull = new LinkedHashMap<>();
        explicitNull.put("requestedCharges", null);
        assertThrows(ApiException.class, () -> RequestedCharges.freeze("conviction", explicitNull));
        assertThrows(ApiException.class, () -> RequestedCharges.freeze("sentencing",
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", "x")))));
    }

    @Test
    void countsUnicodeCodePointsWithoutChangingTheRequest() {
        String value = "😀".repeat(200);
        assertEquals(value, RequestedCharges.freeze("conviction",
                Map.of("requestedCharges", List.of(Map.of("requestedCharge", value)))).get(0).get("requestedCharge"));
    }
}
