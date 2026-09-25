package com.lexcyber.server.engine;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
    private final EngineResultService results;
    private final String serviceToken;

    public EngineResultCallbackController(EngineResultService results, @Value("${engine.service-token}") String serviceToken) {
        this.results = results;
        this.serviceToken = serviceToken;
    }

    @PostMapping("/{executionId}/result")
    public ResponseEntity<Map<String, Object>> result(@PathVariable UUID executionId,
            @RequestHeader(value = "X-Service-Token", defaultValue = "") String token,
            @RequestBody ResultEnvelope payload) {
        if (!MessageDigest.isEqual(serviceToken.getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8))) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("code", "INVALID_SERVICE_TOKEN"));
        }
        if (payload == null || !executionId.equals(payload.executionId())) {
            return ResponseEntity.badRequest().body(Map.of("code", "EXECUTION_ID_MISMATCH"));
        }
        return ResponseEntity.ok(results.accept(payload));
    }
}
