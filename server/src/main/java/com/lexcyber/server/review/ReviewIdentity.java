package com.lexcyber.server.review;

import java.util.Optional;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Trusted proxy identity adapter; production remains fail-closed until an IdP is configured. */
@Component
public class ReviewIdentity {
    private static final Pattern ACTOR = Pattern.compile("[A-Za-z0-9._@:-]{1,200}");
    private final String mode;

    public ReviewIdentity(@Value("${review.auth-mode:disabled}") String mode) {
        this.mode = mode;
    }

    public String require(String header) {
        if (!"trusted-header".equals(mode)) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "review authentication is not configured");
        }
        if (header == null || !ACTOR.matcher(header).matches()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "reviewer identity is required");
        }
        return header;
    }

    public Optional<String> optional(String header) {
        return "trusted-header".equals(mode) && header != null && ACTOR.matcher(header).matches() ? Optional.of(header) : Optional.empty();
    }
}
