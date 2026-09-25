package com.lexcyber.server.engine;

import com.lexcyber.server.settings.ModelAccessService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Internal model-access configuration endpoint for the trusted engine network. */
@RestController
@RequestMapping("/internal/v1/model-access-config")
public class ModelAccessInternalController {
    private final ModelAccessService modelAccess;
    private final String serviceToken;

    public ModelAccessInternalController(ModelAccessService modelAccess,
            @Value("${engine.service-token}") String serviceToken) {
        this.modelAccess = modelAccess;
        this.serviceToken = serviceToken;
    }

    /**
     * Return the effective configuration to the engine after service-token
     * authentication. The returned record intentionally contains the
     * plaintext API key, but this controller does not log it.
     */
    @GetMapping
    public ResponseEntity<?> get(
            @RequestHeader(value = "X-Service-Token", defaultValue = "") String token) {
        if (!MessageDigest.isEqual(serviceToken.getBytes(StandardCharsets.UTF_8),
                token.getBytes(StandardCharsets.UTF_8))) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("code", "INVALID_SERVICE_TOKEN"));
        }
        return ResponseEntity.ok(modelAccess.effectiveConfig());
    }
}
