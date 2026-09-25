package com.lexcyber.server.settings;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class SecretBoxTest {
    @Test
    void property14RoundTripsValidSecretsAndPlaintextsWithoutReturningPlaintext() {
        String[] secrets = {
            "secret-1",
            "longer secret with spaces and punctuation !@#$%^&*()",
            "密钥-配置-🔐",
            "s".repeat(256)
        };
        String[] plaintexts = {
            "",
            "model-api-key",
            "包含中文和 emoji 的 API key 🔑",
            "p".repeat(512)
        };

        for (String secret : secrets) {
            SecretBox box = new SecretBox(secret);
            for (String plaintext : plaintexts) {
                SecretBox.Sealed sealed = box.seal(plaintext);

                assertEquals(plaintext, box.open(sealed.ciphertext(), sealed.nonce()));
                assertFalse(
                        Arrays.equals(sealed.ciphertext(), plaintext.getBytes(StandardCharsets.UTF_8)),
                        "ciphertext must not equal plaintext bytes");
            }
        }
    }

    @Test
    void sealingTheSamePlaintextUsesDifferentNoncesAndCiphertexts() {
        SecretBox box = new SecretBox("stable-test-secret");

        SecretBox.Sealed first = box.seal("same plaintext");
        SecretBox.Sealed second = box.seal("same plaintext");

        assertFalse(Arrays.equals(first.nonce(), second.nonce()));
        assertFalse(Arrays.equals(first.ciphertext(), second.ciphertext()));
    }

    @Test
    void rejectsWrongSecretAndTamperedCiphertextOrNonce() {
        SecretBox box = new SecretBox("correct-secret");
        SecretBox.Sealed sealed = box.seal("authenticated plaintext");

        assertThrows(
                IllegalStateException.class,
                () -> new SecretBox("wrong-secret").open(sealed.ciphertext(), sealed.nonce()));

        byte[] tamperedCiphertext = sealed.ciphertext();
        tamperedCiphertext[0] ^= 0x01;
        assertThrows(
                IllegalStateException.class,
                () -> box.open(tamperedCiphertext, sealed.nonce()));

        byte[] tamperedNonce = sealed.nonce();
        tamperedNonce[0] ^= 0x01;
        assertThrows(
                IllegalStateException.class,
                () -> box.open(sealed.ciphertext(), tamperedNonce));
    }

    @Test
    void emptyOrNullSecretStaysSealedAndNeverFallsBackToPlaintext() {
        for (String secret : new String[] {"", null}) {
            SecretBox box = new SecretBox(secret);

            assertTrue(box.isSealed());
            IllegalStateException sealFailure = assertThrows(
                    IllegalStateException.class, () -> box.seal("must not be stored as plaintext"));
            assertTrue(sealFailure.getMessage().contains("sealed"));
            assertThrows(
                    IllegalStateException.class,
                    () -> box.open(new byte[0], new byte[12]));
        }
    }
}
