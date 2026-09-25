package com.lexcyber.server.review;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import java.util.Optional;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * Resolves the review actor from a bearer session first.
 * Trusted-header remains available for local compose and CI when no session is sent.
 */
@Component
public class ReviewIdentity {
    private static final Pattern ACTOR = Pattern.compile("[A-Za-z0-9._@:-]{1,200}");
    private final String mode;
    private final AuthService auth;

    public ReviewIdentity(@Value("${review.auth-mode:disabled}") String mode, AuthService auth) {
        this.mode = mode;
        this.auth = auth;
    }

    public String require(String authorization, String header) {
        if (auth.hasBearer(authorization)) {
            return auth.require(authorization).username();
        }
        if (!"trusted-header".equals(mode)) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "review authentication is not configured");
        }
        if (header == null || !ACTOR.matcher(header).matches()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "reviewer identity is required");
        }
        return header;
    }

    public Optional<String> optional(String authorization, String header) {
        Optional<AuthAccount> session = auth.resolve(authorization);
        if (session.isPresent()) return session.map(AuthAccount::username);
        return "trusted-header".equals(mode) && header != null && ACTOR.matcher(header).matches()
                ? Optional.of(header)
                : Optional.empty();
    }
}
