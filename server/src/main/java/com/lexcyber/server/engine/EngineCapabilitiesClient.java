package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Reads Engine module capability declarations (INV-RULE-002 / INV-GATE-002). */
@Component
public class EngineCapabilitiesClient {
    private final RestClient client;
    private final String token;

    public EngineCapabilitiesClient(RestClient.Builder builder,
                                    @Value("${engine.base-url}") String baseUrl,
                                    @Value("${engine.service-token}") String token) {
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    /** Whether the Engine has approved rules covering every family the module needs. */
    public boolean moduleAvailable(String module) {
        Capabilities capabilities = capabilities();
        ModuleCapability entry = capabilities == null || capabilities.modules() == null
                ? null : capabilities.modules().get(module);
        return entry != null && entry.available();
    }

    /** Whether an approved template exists for the given doc_type (draft render gate). */
    public boolean templateAvailable(String docType) {
        Capabilities capabilities = capabilities();
        if (capabilities == null || capabilities.templates() == null || docType == null) {
            return false;
        }
        return capabilities.templates().stream()
                .anyMatch(t -> docType.equals(t.docType()));
    }

    public Capabilities capabilities() {
        try {
            return client.get()
                    .uri("/internal/v1/capabilities")
                    .header("X-Service-Token", token)
                    .retrieve()
                    .body(Capabilities.class);
        } catch (Exception ex) {
            return null;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Capabilities(Map<String, ModuleCapability> modules,
                               java.util.List<TemplateCapability> templates) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record TemplateCapability(@JsonProperty("templateId") String templateId,
                                     @JsonProperty("templateVersion") String templateVersion,
                                     @JsonProperty("docType") String docType) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ModuleCapability(boolean available,
                                   @JsonProperty("missingFamilies") List<String> missingFamilies) {
    }
}
