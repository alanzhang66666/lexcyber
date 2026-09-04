package com.lexcyber.server.api;

import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Review mutation is deliberately fail-closed until a real identity provider is
 * configured. The public contract is reserved, but a local demo identity cannot
 * approve or reject a result.
 */
@RestController
@RequestMapping("/v1/reviews")
public class ReviewController {
    @PostMapping("/{reviewId}/approve")
    public ResponseEntity<Map<String, Object>> approve(@PathVariable UUID reviewId) {
        return unavailable(reviewId);
    }

    @PostMapping("/{reviewId}/reject")
    public ResponseEntity<Map<String, Object>> reject(@PathVariable UUID reviewId) {
        return unavailable(reviewId);
    }

    private ResponseEntity<Map<String, Object>> unavailable(UUID reviewId) {
        return ResponseEntity.status(501).body(Map.of(
                "code", "AUTHENTICATION_NOT_CONFIGURED",
                "message", "review mutations require an authenticated identity provider",
                "reviewId", reviewId));
    }
}
