package com.lexcyber.server.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AuthTokensTest {
    @Test
    void parsesBearerTokensCaseInsensitively() {
        assertEquals("abc", AuthTokens.parseBearer("Bearer abc").orElseThrow());
        assertEquals("abc", AuthTokens.parseBearer("bearer abc").orElseThrow());
        assertTrue(AuthTokens.parseBearer("Basic abc").isEmpty());
        assertTrue(AuthTokens.parseBearer("Bearer").isEmpty());
        assertTrue(AuthTokens.parseBearer(null).isEmpty());
    }

    @Test
    void hashesTokensWithoutStoringTheRawValue() {
        String token = AuthTokens.randomToken();
        String hash = AuthTokens.sha256Hex(token);
        assertEquals(64, hash.length());
        assertTrue(token.length() >= 32);
        assertTrue(AuthTokens.sha256Hex(token).equals(hash));
    }
}
