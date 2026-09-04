package com.lexcyber.server.engine;

import java.util.UUID;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClient;

/** Publishes durable outbox rows; a database commit precedes every engine call. */
@Component
public class EngineDispatcher {
    private final JdbcTemplate jdbc;
    private final RestClient client;
    private final String token;
    private final ObjectMapper objectMapper;

    public EngineDispatcher(JdbcTemplate jdbc, RestClient.Builder builder,
                            @Value("${engine.base-url}") String baseUrl,
                            @Value("${engine.service-token}") String token,
                            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.client = builder.baseUrl(baseUrl).build();
        this.token = token;
        this.objectMapper = objectMapper;
    }

    @Scheduled(fixedDelayString = "${engine.dispatch-delay-ms:1000}")
    @Transactional
    public void dispatchOne() {
        jdbc.query("""
                SELECT o.id, o.task_id, o.execution_id, o.payload_json, o.attempts
                FROM app.task_dispatch_outbox o JOIN app.tasks t ON t.id=o.task_id
                WHERE o.published_at IS NULL AND o.next_attempt_at <= now()
                  AND t.status='queued' AND t.execution_id=o.execution_id
                ORDER BY o.id LIMIT 1 FOR UPDATE SKIP LOCKED
                """, rs -> {
            long outboxId = rs.getLong("id");
            try {
                ExecutionRequest request = objectMapper.readValue(rs.getString("payload_json"), ExecutionRequest.class);
                client.post().uri("/internal/v1/executions").header("X-Service-Token", token).body(request).retrieve().toBodilessEntity();
                jdbc.update("UPDATE app.task_dispatch_outbox SET published_at=now(), attempts=attempts+1 WHERE id=?", outboxId);
                jdbc.update("UPDATE app.tasks SET status='running', current_stage='delegated', updated_at=now() WHERE id=? AND execution_id=? AND status='queued'",
                        request.taskId(), request.executionId());
            } catch (Exception failure) {
                int attempts = rs.getInt("attempts") + 1;
                jdbc.update("UPDATE app.task_dispatch_outbox SET attempts=?, last_error=?, next_attempt_at=now() + make_interval(secs => LEAST(60, CAST(power(2, LEAST(?, 6)) AS integer))) WHERE id=?",
                        attempts, failure.getMessage(), rs.getInt("attempts"), outboxId);
                if (attempts >= 20) {
                    jdbc.update("UPDATE app.tasks SET status='failed', current_stage='dispatch_failed', error_code='ENGINE_DISPATCH_EXHAUSTED', error='engine dispatch retry limit exhausted', updated_at=now() WHERE id=? AND status='queued'",
                            rs.getObject("task_id", UUID.class));
                }
            }
        });
    }
}
