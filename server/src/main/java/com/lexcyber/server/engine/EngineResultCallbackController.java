package com.lexcyber.server.engine;

import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Internal, token-protected result callback. Browsers cannot access this route. */
@RestController
@RequestMapping("/internal/v1/executions")
public class EngineResultCallbackController {
    private final JdbcTemplate jdbc;
    private final String serviceToken;

    public EngineResultCallbackController(JdbcTemplate jdbc, @Value("${engine.service-token}") String serviceToken) {
        this.jdbc = jdbc;
        this.serviceToken = serviceToken;
    }

    @PostMapping("/{executionId}/result")
    @Transactional
    public ResponseEntity<Map<String, Object>> result(@PathVariable UUID executionId,
            @RequestHeader(value = "X-Service-Token", defaultValue = "") String token,
            @RequestBody ResultCallback payload) {
        if (!serviceToken.equals(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("code", "INVALID_SERVICE_TOKEN"));
        }
        int updated = jdbc.update("UPDATE app.tasks SET status=?, current_stage=?, updated_at=now() WHERE execution_id=?",
                payload.status(), payload.currentStage(), executionId);
        if (updated == 0) return ResponseEntity.notFound().build();
        jdbc.update("INSERT INTO app.result_versions(result_id, task_id, version, result_type, content_json, content_hash) SELECT ?, id, ?, ?, ?::jsonb, ? FROM app.tasks WHERE execution_id=?",
                payload.resultId(), payload.version(), payload.resultType(), payload.contentJson(), payload.contentHash(), executionId);
        return ResponseEntity.ok(Map.of("status", "accepted", "executionId", executionId));
    }

    public record ResultCallback(UUID resultId, int version, String resultType, String contentJson, String contentHash, String status, String currentStage) {
    }
}
