package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.review.ReviewDecision;
import com.lexcyber.server.review.ReviewIdentity;
import com.lexcyber.server.review.ReviewService;
import jakarta.validation.Valid;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Owner-scoped human-review endpoints. List/get/decide require a bearer session
 * and only expose reviews whose task belongs to a case owned by that account.
 * Decide still binds {@code resultVersion} + pending. Actor comes from the session.
 */
@RestController
@RequestMapping("/v1/reviews")
public class ReviewController {
    private final ReviewService reviews;
    private final ReviewIdentity identity;
    private final AuthService auth;

    public ReviewController(ReviewService reviews, ReviewIdentity identity, AuthService auth) {
        this.reviews = reviews;
        this.identity = identity;
        this.auth = auth;
    }

    @GetMapping
    public Map<String, Object> list(@RequestParam(required = false) String status,
                                    @RequestParam(defaultValue = "0") int page,
                                    @RequestParam(defaultValue = "20") int size,
                                    @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return reviews.list(account.id(), status, page, size);
    }

    @GetMapping("/{reviewId}")
    public Map<String, Object> get(@PathVariable UUID reviewId,
                                   @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return reviews.get(account.id(), reviewId);
    }

    @PostMapping("/{reviewId}/approve")
    public Map<String, Object> approve(@PathVariable UUID reviewId, @Valid @RequestBody ReviewDecision decision,
                                       @RequestHeader(value = "Authorization", required = false) String authorization,
                                       @RequestHeader(value = "X-Reviewer-Id", required = false) String reviewer) {
        AuthAccount account = auth.require(authorization);
        return reviews.decide(account.id(), reviewId, "approve", decision.resultVersion(),
                identity.require(authorization, reviewer), decision.comment());
    }

    @PostMapping("/{reviewId}/reject")
    public Map<String, Object> reject(@PathVariable UUID reviewId, @Valid @RequestBody ReviewDecision decision,
                                      @RequestHeader(value = "Authorization", required = false) String authorization,
                                      @RequestHeader(value = "X-Reviewer-Id", required = false) String reviewer) {
        AuthAccount account = auth.require(authorization);
        return reviews.decide(account.id(), reviewId, "reject", decision.resultVersion(),
                identity.require(authorization, reviewer), decision.comment());
    }
}
