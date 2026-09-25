package com.lexcyber.server.engine;

import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Reconciles terminal Engine states when an asynchronous callback is lost. */
@Component
public class EngineReconciler {
    private static final Logger log = LoggerFactory.getLogger(EngineReconciler.class);
    private final JdbcTemplate jdbc;
    private final RestClient client;
    private final EngineResultService results;
    private final String token;

    public EngineReconciler(JdbcTemplate jdbc, RestClient.Builder builder,
                            @Value("${engine.base-url}") String baseUrl,
                            @Value("${engine.service-token}") String token,
                            EngineResultService results) {
        this.jdbc = jdbc;
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
        this.results = results;
    }

    @Scheduled(fixedDelayString = "${engine.reconcile-delay-ms:2000}")
    public void reconcile() {
        List<UUID> executions = jdbc.query(
                "SELECT execution_id FROM app.tasks WHERE status='running' AND updated_at < now() - interval '2 seconds' ORDER BY updated_at LIMIT 20",
                (rs, ignored) -> rs.getObject("execution_id", UUID.class));
        for (UUID executionId : executions) {
            try {
                ResultEnvelope envelope = client.get().uri("/internal/v1/executions/{id}", executionId)
                        .header("X-Service-Token", token).retrieve().body(ResultEnvelope.class);
                if (envelope != null && !List.of("created", "queued", "claimed", "running").contains(envelope.status())) {
                    results.accept(envelope);
                }
            } catch (RuntimeException failure) {
                log.warn("engine reconciliation failed for {}: {}", executionId, failure.getMessage());
            }
        }
    }
}
