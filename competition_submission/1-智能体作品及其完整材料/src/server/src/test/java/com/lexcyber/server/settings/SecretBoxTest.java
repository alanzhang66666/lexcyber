package com.lexcyber.server.settings;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class SecretBoxTest {
    @Test
    void encryptsAndDecryptsWithoutStoringPlaintext() {
        SecretBox box = new SecretBox("test-encryption-key");
        SecretBox.Sealed sealed = box.seal("sk-test-secret");
        assertFalse(box.isSealed());
        assertNotEquals("sk-test-secret", new String(sealed.ciphertext(), StandardCharsets.UTF_8));
        assertEquals("sk-test-secret", box.open(sealed.ciphertext(), sealed.nonce()));
    }

    @Test
    void refusesToWriteWhenEncryptionKeyIsMissing() {
        assertThrows(IllegalStateException.class, () -> new SecretBox("").seal("secret"));
    }
}
