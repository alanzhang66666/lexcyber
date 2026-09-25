package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Reads the engine's redacted execution trace through the internal boundary. */
@Component
public class EngineTraceClient {
    private final RestClient client;
    private final String token;

    public EngineTraceClient(RestClient.Builder builder,
                             @Value("${engine.base-url}") String baseUrl,
                             @Value("${engine.service-token}") String token) {
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    public List<Map<String, Object>> trace(UUID executionId) {
        EngineTraceResponse response = client.get()
                .uri("/internal/v1/executions/{id}/trace", executionId)
                .header("X-Service-Token", token)
                .retrieve()
                .body(EngineTraceResponse.class);
        return response == null || response.events() == null ? List.of() : response.events();
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record EngineTraceResponse(
            @JsonProperty("executionId") String executionId,
            List<Map<String, Object>> events) {
    }
}
