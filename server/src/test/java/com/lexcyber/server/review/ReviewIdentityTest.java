package com.lexcyber.server.review;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.server.ResponseStatusException;

@ExtendWith(MockitoExtension.class)
class ReviewIdentityTest {
    @Mock
    private AuthService auth;

    @Test
    void prefersABearerSessionOverTheTrustedHeader() {
        when(auth.hasBearer("Bearer tok")).thenReturn(true);
        when(auth.require("Bearer tok")).thenReturn(new AuthAccount(UUID.randomUUID(), "reviewer_01", "审核员"));
        ReviewIdentity identity = new ReviewIdentity("trusted-header", auth);
        assertEquals("reviewer_01", identity.require("Bearer tok", "local-reviewer"));
    }

    @Test
    void fallsBackToTheTrustedHeaderWhenNoSessionIsSent() {
        when(auth.hasBearer(null)).thenReturn(false);
        ReviewIdentity identity = new ReviewIdentity("trusted-header", auth);
        assertEquals("local-reviewer", identity.require(null, "local-reviewer"));
    }

    @Test
    void staysClosedWhenReviewAuthIsDisabledAndNoSessionIsSent() {
        when(auth.hasBearer(null)).thenReturn(false);
        ReviewIdentity identity = new ReviewIdentity("disabled", auth);
        ResponseStatusException error = assertThrows(ResponseStatusException.class, () -> identity.require(null, "local-reviewer"));
        assertEquals(503, error.getStatusCode().value());
    }
}
