package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;

/** Freezes explicit charge requests; it never maps a name to a legal rule key. */
public final class RequestedCharges {
    private RequestedCharges() {}

    public static List<Map<String, Object>> freeze(String module, Map<String, Object> body) {
        if (body == null || body.isEmpty()) return List.of();
        if (!Set.of("requestedCharges").containsAll(body.keySet())) throw invalid();
        if (!body.containsKey("requestedCharges")) return List.of();
        Object raw = body.get("requestedCharges");
        if (!(raw instanceof List<?> items) || items.size() > 32) throw invalid();
        if (!"conviction".equals(module) && !items.isEmpty()) throw invalid();
        List<Map<String, Object>> frozen = new ArrayList<>();
        Set<String> identities = new HashSet<>();
        for (Object item : items) {
            if (!(item instanceof Map<?, ?> fields)
                    || !Set.of("requestedCharge", "chargeKey").containsAll(fields.keySet())) throw invalid();
            Object requested = fields.get("requestedCharge");
            Object key = fields.get("chargeKey");
            if (!validString(requested) || (key != null && !validString(key))) throw invalid();
            String identity = key == null ? "name:" + requested : "key:" + key;
            if (!identities.add(identity)) throw invalid();
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("requestedCharge", requested);
            if (fields.containsKey("chargeKey")) row.put("chargeKey", key);
            frozen.add(Collections.unmodifiableMap(row));
        }
        return List.copyOf(frozen);
    }

    private static boolean validString(Object value) {
        return value instanceof String text && !text.isBlank()
                && text.codePointCount(0, text.length()) <= 200;
    }

    private static ApiException invalid() {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUESTED_CHARGES",
                "请求罪名必须是最多32项明确的名称与可选标识；仅定罪模块支持，标识不得重复");
    }
}
