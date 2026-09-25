package com.lexcyber.server.settings;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * AES-256-GCM encryption for server-side model access secrets.
 *
 * <p>An empty configured secret deliberately leaves this box sealed. It never
 * falls back to storing or returning plaintext.</p>
 */
public final class SecretBox {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final String KEY_ALGORITHM = "AES";
    private static final int KEY_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private final SecretKeySpec key;

    public SecretBox(String secret) {
        this.key = secret == null || secret.isEmpty() ? null : deriveKey(secret);
    }

    public boolean isSealed() {
        return key == null;
    }

    public Sealed seal(String plaintext) {
        requireKey();
        Objects.requireNonNull(plaintext, "plaintext");

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
            return new Sealed(cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8)), nonce);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("unable to encrypt secret", exception);
        }
    }

    public String open(byte[] ciphertext, byte[] nonce) {
        requireKey();
        Objects.requireNonNull(ciphertext, "ciphertext");
        Objects.requireNonNull(nonce, "nonce");

        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
            return new String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("unable to decrypt secret", exception);
        }
    }

    private void requireKey() {
        if (key == null) {
            throw new IllegalStateException("model access configuration is sealed");
        }
    }

    private static SecretKeySpec deriveKey(String secret) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(secret.getBytes(StandardCharsets.UTF_8));
            if (digest.length != KEY_BYTES) {
                throw new IllegalStateException("SHA-256 did not produce an AES-256 key");
            }
            return new SecretKeySpec(digest, KEY_ALGORITHM);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is required", exception);
        }
    }

    public record Sealed(byte[] ciphertext, byte[] nonce) {
        public Sealed {
            Objects.requireNonNull(ciphertext, "ciphertext");
            Objects.requireNonNull(nonce, "nonce");
            ciphertext = ciphertext.clone();
            nonce = nonce.clone();
        }

        @Override
        public byte[] ciphertext() {
            return ciphertext.clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }
    }
}
