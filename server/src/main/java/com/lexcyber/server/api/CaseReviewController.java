package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.review.ReviewOpen;
import com.lexcyber.server.review.ReviewService;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/cases/{caseId}/reviews")
public class CaseReviewController {
    private final AuthService auth;
    private final ReviewService reviews;

    public CaseReviewController(AuthService auth, ReviewService reviews) {
        this.auth = auth;
        this.reviews = reviews;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> open(@PathVariable String caseId,
                                                    @Valid @RequestBody ReviewOpen request,
                                                    @RequestHeader(value = "Authorization", required = false) String authorization,
                                                    @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        AuthAccount account = auth.require(authorization);
        Map<String, Object> opened = idempotencyKey == null
                ? reviews.open(account.id(), caseId, request)
                : reviews.open(account.id(), caseId, request, idempotencyKey);
        return ResponseEntity.status(HttpStatus.CREATED).body(opened);
    }
}
