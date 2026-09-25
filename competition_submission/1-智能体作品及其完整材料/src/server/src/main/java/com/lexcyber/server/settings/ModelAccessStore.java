package com.lexcyber.server.settings;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ModelAccessStore {
    public static final String GLOBAL_SCOPE = "global";
    private final JdbcTemplate jdbc;

    public ModelAccessStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<StoredConfig> findGlobal() {
        List<StoredConfig> rows = jdbc.query("""
                SELECT scope, provider, model_name, api_base_url,
                       api_key_ciphertext, api_key_nonce, api_key_fingerprint,
                       timeout_seconds, updated_by, updated_at
                FROM app.model_access_config WHERE scope = ?
                """, this::map, GLOBAL_SCOPE);
        return rows.stream().findFirst();
    }

    public StoredConfig upsert(ModelAccessConfigUpdate update, byte[] ciphertext,
                               byte[] nonce, String updatedBy) {
        StoredConfig existing = findGlobal().orElse(null);
        String fingerprint;
        if (update.apiKey() == null) {
            if (existing != null) {
                ciphertext = existing.apiKeyCiphertext();
                nonce = existing.apiKeyNonce();
                fingerprint = existing.apiKeyFingerprint();
            } else {
                fingerprint = null;
            }
        } else {
            fingerprint = apiKeyFingerprint(update.apiKey());
        }
        jdbc.update("""
                INSERT INTO app.model_access_config(
                    scope, provider, model_name, api_base_url,
                    api_key_ciphertext, api_key_nonce, api_key_fingerprint,
                    timeout_seconds, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
                ON CONFLICT (scope) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    model_name = EXCLUDED.model_name,
                    api_base_url = EXCLUDED.api_base_url,
                    api_key_ciphertext = EXCLUDED.api_key_ciphertext,
                    api_key_nonce = EXCLUDED.api_key_nonce,
                    api_key_fingerprint = EXCLUDED.api_key_fingerprint,
                    timeout_seconds = EXCLUDED.timeout_seconds,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                """, GLOBAL_SCOPE, update.provider(), update.modelName(), update.apiBaseUrl(),
                ciphertext, nonce, fingerprint, update.timeoutSeconds(), updatedBy);
        return findGlobal().orElseThrow();
    }

    public static String apiKeyFingerprint(String plaintext) {
        if (plaintext == null || plaintext.isEmpty()) return null;
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(plaintext.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest, 0, 6);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is required", exception);
        }
    }

    private StoredConfig map(ResultSet rs, int ignored) throws SQLException {
        double timeout = rs.getDouble("timeout_seconds");
        Double timeoutSeconds = rs.wasNull() ? null : timeout;
        return new StoredConfig(
                rs.getString("scope"), rs.getString("provider"), rs.getString("model_name"),
                rs.getString("api_base_url"), rs.getBytes("api_key_ciphertext"),
                rs.getBytes("api_key_nonce"), rs.getString("api_key_fingerprint"),
                timeoutSeconds, rs.getString("updated_by"),
                rs.getObject("updated_at", OffsetDateTime.class));
    }

    public record StoredConfig(String scope, String provider, String modelName,
            String apiBaseUrl, byte[] apiKeyCiphertext, byte[] apiKeyNonce,
            String apiKeyFingerprint, Double timeoutSeconds, String updatedBy,
            OffsetDateTime updatedAt) {
        public StoredConfig {
            apiKeyCiphertext = apiKeyCiphertext == null ? null : apiKeyCiphertext.clone();
            apiKeyNonce = apiKeyNonce == null ? null : apiKeyNonce.clone();
        }
        @Override public byte[] apiKeyCiphertext() { return apiKeyCiphertext == null ? null : apiKeyCiphertext.clone(); }
        @Override public byte[] apiKeyNonce() { return apiKeyNonce == null ? null : apiKeyNonce.clone(); }
    }
}
