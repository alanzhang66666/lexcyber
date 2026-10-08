package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.lexcyber.server.domain.LegalAnalysisContext;
import java.util.ArrayList;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import java.util.List;
import java.util.UUID;
import java.time.OffsetDateTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RestClient;

/** Applies durable Engine registry invalidations and acknowledges only committed events. */
@Component
public class RegistryInvalidationReconciler {
    private static final Logger log = LoggerFactory.getLogger(RegistryInvalidationReconciler.class);
    private final JdbcTemplate jdbc;
    private final RestClient client;
    private final String token;
    private final TransactionTemplate transactions;

    public RegistryInvalidationReconciler(JdbcTemplate jdbc, RestClient.Builder builder,
                                          @Value("${engine.base-url}") String baseUrl,
                                          @Value("${engine.service-token}") String token,
                                          org.springframework.transaction.PlatformTransactionManager tx) {
        this.jdbc = jdbc;
        var requestFactory = new JdkClientHttpRequestFactory(
                HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                        .connectTimeout(Duration.ofSeconds(5)).build());
        requestFactory.setReadTimeout(Duration.ofSeconds(10));
        this.client = builder.clone().baseUrl(baseUrl).requestFactory(requestFactory).build();
        this.token = token;
        this.transactions = new TransactionTemplate(tx);
    }

    @Scheduled(fixedDelayString = "${engine.registry-invalidation-delay-ms:5000}")
    public void reconcile() {
        InvalidationResponse response;
        try {
            response = client.get().uri(uri -> uri.path("/internal/v1/registry/invalidations")
                            .queryParam("limit", 100).build())
                    .header("X-Service-Token", token).retrieve().body(InvalidationResponse.class);
        } catch (RuntimeException ex) {
            log.warn("registry invalidation pull failed: {}", ex.getMessage());
            return;
        }
        if (response == null || response.events() == null) return;
        for (InvalidationEvent event : response.events()) {
            if (event == null || event.eventId() == null || event.eventId().isBlank()) continue;
            try {
                Boolean applied = transactions.execute(status -> apply(event));
                if (Boolean.TRUE.equals(applied)) {
                    client.post().uri("/internal/v1/registry/invalidations/{id}/ack", event.eventId())
                            .header("X-Service-Token", token)
                            .body(new Ack(true)).retrieve().toBodilessEntity();
                }
            } catch (RuntimeException ex) {
                log.warn("registry invalidation {} failed: {}", event.eventId(), ex.getMessage());
            }
        }
    }

    Boolean apply(InvalidationEvent event) {
        UUID eventId = UUID.fromString(event.eventId());
        if (event.occurredAt() == null || event.dependencies() == null || event.dependencies().isEmpty()) {
            throw new IllegalArgumentException("registry event timestamp and dependencies are required");
        }
        for (Dependency dependency : event.dependencies()) {
            if (dependency == null || dependency.kind() == null
                    || !List.of("rule", "legal_source", "template").contains(dependency.kind())
                    || blank(dependency.key()) || blank(dependency.version())) {
                throw new IllegalArgumentException("malformed registry invalidation dependency");
            }
        }
        // Even a duplicate receipt acquires the barrier before touching application locks.
        jdbc.queryForList("SELECT pg_advisory_xact_lock_shared(?)",
                (Object) EngineRegistryClient.REGISTRY_BARRIER);
        Long seen = jdbc.queryForObject("SELECT COUNT(*) FROM app.registry_invalidation_applied WHERE event_id = ?::uuid",
                Long.class, eventId);
        if (seen != null && seen > 0) return true;
        List<UUID> initial = affectedArtifacts(event);
        List<String> cases = affectedCases(initial);
        cases.forEach(caseId -> LegalAnalysisContext.lockCase(jdbc, caseId));
        // Publication takes the same case lock. Re-read its closure after locking:
        // consumers committed while we were waiting must be marked stale as well.
        List<UUID> invalid = affectedArtifacts(event);
        if (!cases.containsAll(affectedCases(invalid))) {
            throw new IllegalStateException("registry dependency closure gained an unlocked case; retry event");
        }
        if (!invalid.isEmpty()) {
            UUID[] ids = invalid.toArray(UUID[]::new);
            jdbc.update("UPDATE app.module_head SET stale=true, stale_reason='dependency_changed', updated_at=now() WHERE confirmed_version_id = ANY(?)", (Object) ids);
            jdbc.update("UPDATE app.draft_head SET stale=true, stale_reason='dependency_changed', updated_at=now() WHERE approved_version_id = ANY(?)", (Object) ids);
        }
        jdbc.update("INSERT INTO app.registry_invalidation_applied(event_id) VALUES (?::uuid) ON CONFLICT DO NOTHING", eventId);
        return true;
    }

    private List<UUID> affectedArtifacts(InvalidationEvent event) {
        List<UUID> invalid = new ArrayList<>();
        for (Dependency dependency : event.dependencies()) {
            invalid.addAll(jdbc.query("""
                    WITH RECURSIVE roots(artifact_version_id) AS (
                        SELECT e.artifact_version_id FROM app.artifact_external_dependency e
                        JOIN app.artifact_version av ON av.artifact_version_id = e.artifact_version_id
                        WHERE e.dependency_kind = ? AND e.dependency_key = ?
                          AND (e.dependency_version = ? OR e.dependency_version = '')
                          AND av.created_at <= ?
                    ), affected(artifact_version_id) AS (
                        SELECT artifact_version_id FROM roots
                        UNION
                        SELECT d.artifact_version_id FROM app.artifact_artifact_dependency d
                        JOIN affected a ON a.artifact_version_id = d.depends_on_artifact_version_id
                    ) SELECT artifact_version_id FROM affected
                    """, (rs, ignored) -> rs.getObject(1, UUID.class), dependency.kind(),
                    dependency.key(), dependency.version(), event.occurredAt()));
        }
        return invalid.stream().distinct().toList();
    }

    private List<String> affectedCases(List<UUID> artifacts) {
        if (artifacts.isEmpty()) return List.of();
        return jdbc.query("""
                SELECT DISTINCT s.case_id::text
                FROM app.artifact_version v JOIN app.artifact_stream s
                  ON s.artifact_stream_id = v.artifact_stream_id
                WHERE v.artifact_version_id = ANY(?)
                ORDER BY s.case_id::text
                """, (rs, ignored) -> rs.getString(1), (Object) artifacts.toArray(UUID[]::new));
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record InvalidationResponse(List<InvalidationEvent> events) {}
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record InvalidationEvent(String eventId, OffsetDateTime occurredAt,
                                    List<Dependency> dependencies) {}
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Dependency(String kind, String key, String version) {}
    public record Ack(boolean acknowledged) {}
}
