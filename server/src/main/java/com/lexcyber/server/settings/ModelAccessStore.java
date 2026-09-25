package com.lexcyber.server.settings;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * JDBC access for the deployment-wide model access configuration.
 *
 * <p>The table is intentionally a one-row store keyed by {@code scope=global}.
 * Ciphertext and nonce are kept as byte arrays and are never projected into the
 * public configuration view.</p>
 */
@Repository
public class ModelAccessStore {
    public static final String GLOBAL_SCOPE = "global";
    private static final String SELECT_GLOBAL = """
            SELECT scope, provider, model_name, api_base_url,
                   api_key_ciphertext, api_key_nonce, api_key_fingerprint,
                   timeout_seconds, updated_by, updated_at
            FROM app.model_access_config
            WHERE scope = ?
            """;

    private final JdbcTemplate jdbc;

    public ModelAccessStore(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    /** Return the stored global row, if one has been written. */
    public Optional<StoredConfig> findGlobal() {
        List<StoredConfig> rows = jdbc.query(SELECT_GLOBAL, this::map, GLOBAL_SCOPE);
        return rows.stream().findFirst();
    }

    /**
     * Insert or replace the global row.
     *
     * <p>{@code apiKeyPlaintext} is used only to derive the short fingerprint.
     * Passing {@code null} preserves the existing key material and fingerprint;
     * passing an empty string clears them.</p>
     */
    public StoredConfig upsert(String provider,
                               String modelName,
                               String apiBaseUrl,
                               Number timeoutSeconds,
                               byte[] apiKeyCiphertext,
                               byte[] apiKeyNonce,
                               String apiKeyPlaintext,
                               String updatedBy) {
        Objects.requireNonNull(timeoutSeconds, "timeoutSeconds");

        StoredConfig existing = null;
        if (apiKeyPlaintext == null && apiKeyCiphertext == null && apiKeyNonce == null) {
            existing = findGlobal().orElse(null);
            if (existing != null) {
                apiKeyCiphertext = existing.apiKeyCiphertext();
                apiKeyNonce = existing.apiKeyNonce();
            }
        }
        String fingerprint = existing == null
                ? fingerprintForWrite(apiKeyPlaintext, apiKeyCiphertext, apiKeyNonce)
                : existing.apiKeyFingerprint();
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
                """, GLOBAL_SCOPE, provider, modelName, apiBaseUrl,
                apiKeyCiphertext, apiKeyNonce, fingerprint, timeoutSeconds, updatedBy);
        return findGlobal().orElseThrow(() ->
                new IllegalStateException("model access configuration was not stored"));
    }

    /** Store an update DTO together with the ciphertext produced by SecretBox. */
    public StoredConfig upsert(ModelAccessConfigUpdate update,
                               byte[] apiKeyCiphertext,
                               byte[] apiKeyNonce,
                               String updatedBy) {
        Objects.requireNonNull(update, "update");
        return upsert(update.provider(), update.modelName(), update.apiBaseUrl(),
                update.timeoutSeconds(), apiKeyCiphertext, apiKeyNonce,
                update.apiKey(), updatedBy);
    }

    /** SHA-256 fingerprint used in storage and audit metadata; never returns key material. */
    public static String apiKeyFingerprint(String plaintext) {
        if (plaintext == null || plaintext.isEmpty()) {
            return null;
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(plaintext.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest, 0, 6);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is required", exception);
        }
    }

    private String fingerprintForWrite(String plaintext, byte[] ciphertext, byte[] nonce) {
        if (plaintext != null) {
            return apiKeyFingerprint(plaintext);
        }
        if (ciphertext == null && nonce == null) {
            return null;
        }
        return findGlobal().map(StoredConfig::apiKeyFingerprint).orElse(null);
    }

    private StoredConfig map(ResultSet rs, int ignored) throws SQLException {
        double timeout = rs.getDouble("timeout_seconds");
        Double timeoutSeconds = rs.wasNull() ? null : timeout;
        return new StoredConfig(
                rs.getString("scope"),
                rs.getString("provider"),
                rs.getString("model_name"),
                rs.getString("api_base_url"),
                rs.getBytes("api_key_ciphertext"),
                rs.getBytes("api_key_nonce"),
                rs.getString("api_key_fingerprint"),
                timeoutSeconds,
                rs.getString("updated_by"),
                rs.getObject("updated_at", OffsetDateTime.class));
    }

    /** Internal storage row; it contains ciphertext, never a plaintext API key. */
    public record StoredConfig(
            String scope,
            String provider,
            String modelName,
            String apiBaseUrl,
            byte[] apiKeyCiphertext,
            byte[] apiKeyNonce,
            String apiKeyFingerprint,
            Double timeoutSeconds,
            String updatedBy,
            OffsetDateTime updatedAt) {
        public StoredConfig {
            apiKeyCiphertext = apiKeyCiphertext == null ? null : apiKeyCiphertext.clone();
            apiKeyNonce = apiKeyNonce == null ? null : apiKeyNonce.clone();
        }

        @Override
        public byte[] apiKeyCiphertext() {
            return apiKeyCiphertext == null ? null : apiKeyCiphertext.clone();
        }

        @Override
        public byte[] apiKeyNonce() {
            return apiKeyNonce == null ? null : apiKeyNonce.clone();
        }
    }
}
