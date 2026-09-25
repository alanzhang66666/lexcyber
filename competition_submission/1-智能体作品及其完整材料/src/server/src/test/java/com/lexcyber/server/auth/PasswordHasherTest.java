package com.lexcyber.server.auth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class PasswordHasherTest {
    @Test
    void hashesAndVerifiesAPassword() {
        String stored = PasswordHasher.hash("password1");
        assertTrue(stored.startsWith("pbkdf2$" + PasswordHasher.ITERATIONS + "$"));
        assertTrue(PasswordHasher.matches("password1", stored));
        assertFalse(PasswordHasher.matches("password2", stored));
        assertFalse(PasswordHasher.matches("password1", "not-a-hash"));
    }
}
