package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.lexcyber.server.api.ApiException;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class EngineImportClient {
    private final RestClient client;
    private final String token;

    public EngineImportClient(RestClient.Builder builder,
                              @Value("${engine.base-url}") String baseUrl,
                              @Value("${engine.service-token}") String token) {
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    public ValidationResponse validate(String storageKey, String rawSha256) {
        try {
            ValidationResponse response = client.post()
                    .uri("/internal/v1/imports/validate")
                    .header("X-Service-Token", token)
                    .body(Map.of("storage_key", storageKey, "raw_sha256", rawSha256))
                    .retrieve()
                    .body(ValidationResponse.class);
            if (response == null) {
                throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_UNAVAILABLE",
                        "engine import validation returned no response");
            }
            return response;
        } catch (ApiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_UNAVAILABLE",
                    "engine import validation failed", ex);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ValidationResponse(
            boolean valid,
            @JsonProperty("schema_version") String schemaVersion,
            @JsonProperty("package_id") String packageId,
            @JsonProperty("producer_id") String producerId,
            @JsonProperty("dataset_id") String datasetId,
            String revision,
            @JsonProperty("package_digest") String packageDigest,
            List<Map<String, Object>> items,
            List<Map<String, Object>> errors) {
    }
}
