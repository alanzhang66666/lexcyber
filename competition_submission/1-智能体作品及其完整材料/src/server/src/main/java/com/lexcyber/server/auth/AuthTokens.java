package com.lexcyber.server.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Optional;

final class AuthTokens {
    private static final SecureRandom RANDOM = new SecureRandom();

    private AuthTokens() {
    }

    static String randomToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static String sha256Hex(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte item : digest) result.append(String.format("%02x", item & 0xff));
            return result.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is required", ex);
        }
    }

    static Optional<String> parseBearer(String authorization) {
        if (authorization == null) return Optional.empty();
        String value = authorization.trim();
        if (value.length() < 8 || !value.regionMatches(true, 0, "Bearer ", 0, 7)) return Optional.empty();
        String token = value.substring(7).trim();
        return token.isEmpty() ? Optional.empty() : Optional.of(token);
    }
}
