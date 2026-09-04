package com.lexcyber.server.engine;

import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Publishes durable outbox rows; a database commit precedes every engine call. */
@Component
public class EngineDispatcher {
    private final JdbcTemplate jdbc;
    private final RestClient client;
    private final String token;

    public EngineDispatcher(JdbcTemplate jdbc, RestClient.Builder builder,
                            @Value("${engine.base-url}") String baseUrl,
                            @Value("${engine.service-token}") String token) {
        this.jdbc = jdbc;
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
    }

    @Scheduled(fixedDelayString = "${engine.dispatch-delay-ms:1000}")
    public void dispatchOne() {
        jdbc.query("""
                SELECT o.id, o.task_id, o.execution_id, t.request_id, t.query_text, t.case_id, t.metadata_json
                FROM app.task_dispatch_outbox o JOIN app.tasks t ON t.id=o.task_id
                WHERE o.published_at IS NULL ORDER BY o.id LIMIT 1
                """, rs -> {
            long outboxId = rs.getLong("id");
            try {
                Map<String, Object> payload = Map.of(
                        "task_id", rs.getObject("task_id", UUID.class),
                        "execution_id", rs.getObject("execution_id", UUID.class),
                        "request_id", rs.getObject("request_id", UUID.class),
                        "query", rs.getString("query_text"),
                        "case_id", rs.getString("case_id"),
                        "metadata", Map.of());
                client.post().uri("/internal/v1/executions").header("X-Service-Token", token).body(payload).retrieve().toBodilessEntity();
                jdbc.update("UPDATE app.task_dispatch_outbox SET published_at=now(), attempts=attempts+1 WHERE id=?", outboxId);
                jdbc.update("UPDATE app.tasks SET status='running', current_stage='delegated', updated_at=now() WHERE id=?", payload.get("task_id"));
            } catch (RuntimeException failure) {
                jdbc.update("UPDATE app.task_dispatch_outbox SET attempts=attempts+1 WHERE id=?", outboxId);
            }
        });
    }
}
