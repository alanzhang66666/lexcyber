package com.lexcyber.server.api;

import java.util.UUID;
import java.util.Map;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestBody;
import com.lexcyber.server.review.ReviewDecision;
import com.lexcyber.server.review.ReviewIdentity;
import com.lexcyber.server.review.ReviewService;

/** Public human-review endpoints; identity is supplied only by the configured adapter. */
@RestController
@RequestMapping("/v1/reviews")
public class ReviewController {
    private final ReviewService reviews;
    private final ReviewIdentity identity;

    public ReviewController(ReviewService reviews, ReviewIdentity identity) {
        this.reviews = reviews;
        this.identity = identity;
    }

    @org.springframework.web.bind.annotation.GetMapping
    public Map<String, Object> list(@org.springframework.web.bind.annotation.RequestParam(required = false) String status,
                                    @org.springframework.web.bind.annotation.RequestParam(defaultValue = "0") int page,
                                    @org.springframework.web.bind.annotation.RequestParam(defaultValue = "20") int size) {
        return reviews.list(status, page, size);
    }

    @org.springframework.web.bind.annotation.GetMapping("/{reviewId}")
    public Map<String, Object> get(@PathVariable UUID reviewId) {
        return reviews.get(reviewId);
    }

    @PostMapping("/{reviewId}/approve")
    public Map<String, Object> approve(@PathVariable UUID reviewId, @Valid @RequestBody ReviewDecision decision,
                                       @RequestHeader(value = "X-Reviewer-Id", required = false) String reviewer) {
        return reviews.decide(reviewId, "approve", decision.resultVersion(), identity.require(reviewer), decision.comment());
    }

    @PostMapping("/{reviewId}/reject")
    public Map<String, Object> reject(@PathVariable UUID reviewId, @Valid @RequestBody ReviewDecision decision,
                                      @RequestHeader(value = "X-Reviewer-Id", required = false) String reviewer) {
        return reviews.decide(reviewId, "reject", decision.resultVersion(), identity.require(reviewer), decision.comment());
    }
}
