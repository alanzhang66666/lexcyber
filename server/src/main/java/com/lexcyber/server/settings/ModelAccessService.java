package com.lexcyber.server.settings;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Resolves and stores the deployment-wide model access configuration.
 *
 * <p>The environment is the fallback source. A stored global row overrides
 * each non-empty field independently. API key material is deliberately kept
 * out of the public view and out of audit/log messages.</p>
 */
@Service
public class ModelAccessService {
    private static final Logger log = LoggerFactory.getLogger(ModelAccessService.class);

    private static final String ENVIRONMENT_SOURCE = "environment";
    private static final String STORED_SOURCE = "stored";
    private static final String DEFAULT_PROVIDER = "stub";
    private static final String DEFAULT_MODEL_NAME = "stub-general-v1";
    private static final String DEFAULT_API_BASE_URL = "https://api.openai.com/v1";
    private static final double DEFAULT_TIMEOUT_SECONDS = 45.0;

    private final ModelAccessStore store;
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final SecretBox secretBox;
    private final String environmentProvider;
    private final String environmentModelName;
    private final String environmentApiBaseUrl;
    private final String environmentApiKey;
    private final double environmentTimeoutSeconds;
    private final Set<String> allowedApiBaseUrls;

    /** Spring construction using the application.yml/environment placeholders. */
    @Autowired
    public ModelAccessService(
            ModelAccessStore store,
            JdbcTemplate jdbc,
            ObjectMapper objectMapper,
            @Value("${model-access.encryption-key:}") String encryptionKey,
            @Value("${MODEL_PROVIDER:stub}") String provider,
            @Value("${MODEL_NAME:stub-general-v1}") String modelName,
            @Value("${MODEL_API_BASE_URL:https://api.openai.com/v1}") String apiBaseUrl,
            @Value("${MODEL_API_KEY:}") String apiKey,
            @Value("${MODEL_TIMEOUT_SECONDS:45}") String timeoutSeconds,
            @Value("${MODEL_API_BASE_URL_ALLOWLIST:}") String apiBaseUrlAllowlist) {
        this(store, jdbc, objectMapper, new SecretBox(encryptionKey),
                provider, modelName, apiBaseUrl, apiKey, parseTimeout(timeoutSeconds), apiBaseUrlAllowlist);
    }

    /**
     * Constructor useful for unit tests and for callers that already own the
     * configured SecretBox. The Spring constructor above remains the only
     * constructor selected by dependency injection.
     */
    public ModelAccessService(
            ModelAccessStore store,
            JdbcTemplate jdbc,
            ObjectMapper objectMapper,
            SecretBox secretBox,
            String provider,
            String modelName,
            String apiBaseUrl,
            String apiKey,
            double timeoutSeconds) {
        this(store, jdbc, objectMapper, secretBox, provider, modelName, apiBaseUrl, apiKey,
                timeoutSeconds, "");
    }

    public ModelAccessService(
            ModelAccessStore store,
            JdbcTemplate jdbc,
            ObjectMapper objectMapper,
            SecretBox secretBox,
            String provider,
            String modelName,
            String apiBaseUrl,
            String apiKey,
            double timeoutSeconds,
            String apiBaseUrlAllowlist) {
        this.store = Objects.requireNonNull(store, "store");
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
        this.secretBox = Objects.requireNonNull(secretBox, "secretBox");
        this.environmentProvider = fallback(provider, DEFAULT_PROVIDER);
        this.environmentModelName = fallback(modelName, DEFAULT_MODEL_NAME);
        this.environmentApiBaseUrl = fallback(apiBaseUrl, DEFAULT_API_BASE_URL);
        this.environmentApiKey = apiKey == null ? "" : apiKey;
        this.environmentTimeoutSeconds = validTimeout(timeoutSeconds)
                ? timeoutSeconds : DEFAULT_TIMEOUT_SECONDS;
        this.allowedApiBaseUrls = parseBaseUrlAllowlist(apiBaseUrlAllowlist, this.environmentApiBaseUrl);
    }

    /** Return the effective public configuration without returning key material. */
    @Transactional(readOnly = true)
    public ModelAccessConfigView get() {
        return toView(resolveState(store.findGlobal()));
    }

    /**
     * Return the effective configuration for the trusted in-process engine
     * adapter. This is intentionally separate from {@link #get()} because the
     * returned key must never cross the public API boundary.
     */
    @Transactional(readOnly = true)
    public EffectiveConfig effectiveConfig() {
        Optional<ModelAccessStore.StoredConfig> stored = store.findGlobal();
        EffectiveState state = resolveState(stored);
        String apiKey = environmentApiKey;
        if (hasStoredApiKey(stored.orElse(null))) {
            ModelAccessStore.StoredConfig row = stored.orElseThrow();
            if (secretBox.isSealed()) {
                throw sealed("已存密钥无法解密，请重新填写 API Key");
            }
            try {
                apiKey = secretBox.open(row.apiKeyCiphertext(), row.apiKeyNonce());
            } catch (IllegalStateException failure) {
                throw sealed("已存密钥无法解密，请重新填写 API Key", failure);
            }
        }
        return new EffectiveConfig(
                state.provider(), state.modelName(), state.apiBaseUrl(), apiKey,
                state.timeoutSeconds(), state.source());
    }

    /**
     * Persist a global configuration update and append one business-audit row.
     * A null API key keeps the existing stored ciphertext, an empty API key
     * clears it, and a non-empty API key is sealed before it reaches the store.
     */
    @Transactional
    public ModelAccessConfigView update(UUID accountId, ModelAccessConfigUpdate update) {
        Objects.requireNonNull(accountId, "accountId");
        if (update == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_MODEL_CONFIG", "model config is required");
        }
        String requestedBaseUrl = canonicalBaseUrl(update.apiBaseUrl());
        if (!allowedApiBaseUrls.contains(requestedBaseUrl)) {
            throw new ApiException(
                    HttpStatus.FORBIDDEN,
                    "MODEL_ENDPOINT_NOT_ALLOWED",
                    "model API base URL is not allowlisted");
        }

        Optional<ModelAccessStore.StoredConfig> beforeStored = store.findGlobal();
        EffectiveState before = resolveState(beforeStored);

        byte[] ciphertext = null;
        byte[] nonce = null;
        if (update.apiKey() == null) {
            ModelAccessStore.StoredConfig row = beforeStored.orElse(null);
            if (hasStoredApiKey(row)) {
                ciphertext = row.apiKeyCiphertext();
                nonce = row.apiKeyNonce();
            }
        } else if (!update.apiKey().isEmpty()) {
            if (secretBox.isSealed()) {
                throw sealed("服务端未配置配置加密密钥，无法保存 API Key");
            }
            try {
                SecretBox.Sealed sealed = secretBox.seal(update.apiKey());
                ciphertext = sealed.ciphertext();
                nonce = sealed.nonce();
            } catch (IllegalStateException failure) {
                throw sealed("服务端未配置配置加密密钥，无法保存 API Key", failure);
            }
        }

        ModelAccessStore.StoredConfig saved = store.upsert(
                update, ciphertext, nonce, accountId.toString());
        EffectiveState after = resolveState(Optional.of(saved));
        List<String> changedFields = changedFields(before, after, update.apiKey() != null);
        boolean apiKeyChanged = changedFields.contains("apiKey");

        writeAudit(accountId, changedFields, after.provider(), after.modelName(),
                apiKeyChanged, saved.apiKeyFingerprint());
        log.info("model access config updated provider={} model={} apiKeyChanged={}",
                after.provider(), after.modelName(), apiKeyChanged);
        return toView(after);
    }

    private EffectiveState resolveState(Optional<ModelAccessStore.StoredConfig> stored) {
        ModelAccessStore.StoredConfig row = stored.orElse(null);
        boolean storedApiKey = hasStoredApiKey(row);
        String fingerprint = storedApiKey && row.apiKeyFingerprint() != null
                ? row.apiKeyFingerprint()
                : ModelAccessStore.apiKeyFingerprint(environmentApiKey);
        return new EffectiveState(
                choose(row == null ? null : row.provider(), environmentProvider),
                choose(row == null ? null : row.modelName(), environmentModelName),
                choose(row == null ? null : row.apiBaseUrl(), environmentApiBaseUrl),
                chooseTimeout(row == null ? null : row.timeoutSeconds()),
                storedApiKey || !environmentApiKey.isBlank(),
                fingerprint,
                row == null ? ENVIRONMENT_SOURCE : STORED_SOURCE,
                row == null ? null : row.updatedBy(),
                row == null ? null : row.updatedAt());
    }

    private ModelAccessConfigView toView(EffectiveState state) {
        return new ModelAccessConfigView(
                state.provider(), state.modelName(), state.apiBaseUrl(), state.timeoutSeconds(),
                state.apiKeyConfigured(), ModelAccessConfigView.API_KEY_MASK, state.source(),
                state.updatedBy(), state.updatedAt());
    }

    private List<String> changedFields(EffectiveState before, EffectiveState after, boolean apiKeyWasSubmitted) {
        List<String> changed = new ArrayList<>();
        if (!Objects.equals(before.provider(), after.provider())) {
            changed.add("provider");
        }
        if (!Objects.equals(before.modelName(), after.modelName())) {
            changed.add("modelName");
        }
        if (!Objects.equals(before.apiBaseUrl(), after.apiBaseUrl())) {
            changed.add("apiBaseUrl");
        }
        if (apiKeyWasSubmitted && !Objects.equals(before.apiKeyFingerprint(), after.apiKeyFingerprint())) {
            changed.add("apiKey");
        }
        if (Double.compare(before.timeoutSeconds(), after.timeoutSeconds()) != 0) {
            changed.add("timeoutSeconds");
        }
        return List.copyOf(changed);
    }

    private void writeAudit(UUID accountId, List<String> changedFields, String provider,
                            String model, boolean apiKeyChanged, String apiKeyFingerprint) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("changedFields", changedFields);
        payload.put("provider", provider);
        payload.put("model", model);
        payload.put("apiKeyChanged", apiKeyChanged);
        payload.put("apiKeyFingerprint", apiKeyFingerprint);
        jdbc.update("""
                INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                VALUES (?, 'model.access.updated', 'model_access_config', 'global', ?::jsonb)
                """, "account:" + accountId, writeJson(payload));
    }

    private String writeJson(Map<String, Object> payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException failure) {
            throw new IllegalStateException("unable to serialize model access audit", failure);
        }
    }

    private ApiException sealed(String message) {
        return sealed(message, null);
    }

    private ApiException sealed(String message, Throwable cause) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_CONFIG_SEALED", message, cause);
    }

    private boolean hasStoredApiKey(ModelAccessStore.StoredConfig row) {
        return row != null && row.apiKeyCiphertext() != null && row.apiKeyNonce() != null;
    }

    private double chooseTimeout(Double stored) {
        return stored != null && validTimeout(stored) ? stored : environmentTimeoutSeconds;
    }

    private static String choose(String stored, String environment) {
        return stored == null || stored.isBlank() ? environment : stored;
    }

    private static String fallback(String value, String defaultValue) {
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private static double parseTimeout(String value) {
        if (value == null || value.isBlank()) {
            return DEFAULT_TIMEOUT_SECONDS;
        }
        try {
            double parsed = Double.parseDouble(value);
            return validTimeout(parsed) ? parsed : DEFAULT_TIMEOUT_SECONDS;
        } catch (NumberFormatException ignored) {
            return DEFAULT_TIMEOUT_SECONDS;
        }
    }

    private static boolean validTimeout(double value) {
        return Double.isFinite(value) && value > 0;
    }

    private static Set<String> parseBaseUrlAllowlist(String configured, String environmentBaseUrl) {
        if (configured == null || configured.isBlank()) {
            return Set.of(canonicalBaseUrl(environmentBaseUrl));
        }
        return Arrays.stream(configured.split(","))
                .map(ModelAccessService::canonicalBaseUrl)
                .filter(value -> !value.isBlank())
                .collect(Collectors.toUnmodifiableSet());
    }

    private static String canonicalBaseUrl(String value) {
        if (value == null) {
            return "";
        }
        String normalized = value.trim();
        while (normalized.endsWith("/") && normalized.length() > "https://".length()) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        return normalized;
    }

    /** Effective configuration for the trusted internal engine path. */
    public record EffectiveConfig(
            String provider,
            String modelName,
            String apiBaseUrl,
            String apiKey,
            Double timeoutSeconds,
            String source) {
    }

    private record EffectiveState(
            String provider,
            String modelName,
            String apiBaseUrl,
            Double timeoutSeconds,
            boolean apiKeyConfigured,
            String apiKeyFingerprint,
            String source,
            String updatedBy,
            OffsetDateTime updatedAt) {
    }
}
