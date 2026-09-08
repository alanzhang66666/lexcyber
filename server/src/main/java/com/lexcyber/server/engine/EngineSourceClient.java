package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.SourceSearchHit;
import com.lexcyber.server.domain.SourceSearchRequest;
import com.lexcyber.server.domain.SourceSearchResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/** Calls the Engine retrieval adapter. Never talks to a vector store directly. */
@Component
public class EngineSourceClient {
    private final RestClient client;
    private final String token;

    public EngineSourceClient(RestClient.Builder builder,
                              @Value("${engine.base-url}") String baseUrl,
                              @Value("${engine.service-token}") String token) {
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    public SourceSearchResponse search(SourceSearchRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("query", request.query());
        body.put("jurisdiction", request.jurisdiction());
        body.put("as_of_date", request.asOfDate() == null ? null : request.asOfDate().toString());
        body.put("top_k", request.topK() == null ? 5 : request.topK());
        try {
            EngineSearchResponse response = client.post()
                    .uri("/internal/v1/sources/search")
                    .header("X-Service-Token", token)
                    .body(body)
                    .retrieve()
                    .body(EngineSearchResponse.class);
            List<SourceSearchHit> items = response == null || response.items() == null
                    ? List.of()
                    : response.items().stream()
                    .map(item -> new SourceSearchHit(item.sourceId(), item.locator(), item.title(),
                            item.quote(), item.version(), item.jurisdiction()))
                    .toList();
            return new SourceSearchResponse(items);
        } catch (RestClientResponseException ex) {
            if (ex.getStatusCode().value() == 501) {
                throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "SOURCE_SEARCH_UNAVAILABLE", "法源检索尚未接通");
            }
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_UNAVAILABLE", "engine search failed", ex);
        } catch (ApiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_UNAVAILABLE", "engine search failed", ex);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record EngineSearchHit(
            @JsonProperty("source_id") String sourceId,
            String locator,
            String title,
            String quote,
            String version,
            String jurisdiction) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record EngineSearchResponse(List<EngineSearchHit> items) {
    }
}
