package com.lexcyber.server.settings;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ModelAccessService {
    private final ModelAccessStore store;
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;
    private final SecretBox secretBox;
    private final String environmentProvider;
    private final String environmentModelName;
    private final String environmentApiBaseUrl;
    private final String environmentApiKey;
    private final double environmentTimeoutSeconds;

    public ModelAccessService(ModelAccessStore store, JdbcTemplate jdbc, ObjectMapper objectMapper,
            @Value("${model-access.encryption-key:}") String encryptionKey,
            @Value("${MODEL_PROVIDER:stub}") String provider,
            @Value("${MODEL_NAME:stub-general-v1}") String modelName,
            @Value("${MODEL_API_BASE_URL:https://api.openai.com/v1}") String apiBaseUrl,
            @Value("${MODEL_API_KEY:}") String apiKey,
            @Value("${MODEL_TIMEOUT_SECONDS:45}") String timeoutSeconds) {
        this.store = store;
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
        this.secretBox = new SecretBox(encryptionKey);
        this.environmentProvider = fallback(provider, "stub");
        this.environmentModelName = fallback(modelName, "stub-general-v1");
        this.environmentApiBaseUrl = fallback(apiBaseUrl, "https://api.openai.com/v1");
        this.environmentApiKey = apiKey == null ? "" : apiKey;
        this.environmentTimeoutSeconds = parseTimeout(timeoutSeconds);
    }

    @Transactional(readOnly = true)
    public ModelAccessConfigView get() {
        return toView(resolve(store.findGlobal()));
    }

    @Transactional(readOnly = true)
    public EffectiveConfig effectiveConfig() {
        Optional<ModelAccessStore.StoredConfig> stored = store.findGlobal();
        EffectiveState state = resolve(stored);
        String apiKey = environmentApiKey;
        ModelAccessStore.StoredConfig row = stored.orElse(null);
        if (hasStoredKey(row)) {
            if (secretBox.isSealed()) {
                throw sealed("已存 API Key 无法解密，请配置加密密钥后重新填写");
            }
            try {
                apiKey = secretBox.open(row.apiKeyCiphertext(), row.apiKeyNonce());
            } catch (IllegalStateException failure) {
                throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_CONFIG_SEALED",
                        "已存 API Key 无法解密，请重新填写", failure);
            }
        }
        return new EffectiveConfig(state.provider(), state.modelName(), state.apiBaseUrl(),
                apiKey, state.timeoutSeconds(), state.source());
    }

    @Transactional
    public ModelAccessConfigView update(UUID accountId, ModelAccessConfigUpdate update) {
        Optional<ModelAccessStore.StoredConfig> beforeStored = store.findGlobal();
        EffectiveState before = resolve(beforeStored);
        byte[] ciphertext = null;
        byte[] nonce = null;
        if (update.apiKey() != null && !update.apiKey().isEmpty()) {
            if (secretBox.isSealed()) {
                throw sealed("服务端未配置模型配置加密密钥，无法保存 API Key");
            }
            SecretBox.Sealed sealed = secretBox.seal(update.apiKey());
            ciphertext = sealed.ciphertext();
            nonce = sealed.nonce();
        }
        ModelAccessStore.StoredConfig saved = store.upsert(update, ciphertext, nonce, accountId.toString());
        EffectiveState after = resolve(Optional.of(saved));
        List<String> changed = changedFields(before, after, update.apiKey() != null);
        writeAudit(accountId, changed, after, saved.apiKeyFingerprint());
        return toView(after);
    }

    private EffectiveState resolve(Optional<ModelAccessStore.StoredConfig> stored) {
        ModelAccessStore.StoredConfig row = stored.orElse(null);
        boolean storedKey = hasStoredKey(row);
        return new EffectiveState(
                choose(row == null ? null : row.provider(), environmentProvider),
                choose(row == null ? null : row.modelName(), environmentModelName),
                choose(row == null ? null : row.apiBaseUrl(), environmentApiBaseUrl),
                row != null && row.timeoutSeconds() != null ? row.timeoutSeconds() : environmentTimeoutSeconds,
                storedKey || !environmentApiKey.isBlank(),
                storedKey ? row.apiKeyFingerprint() : ModelAccessStore.apiKeyFingerprint(environmentApiKey),
                row == null ? "environment" : "stored",
                row == null ? null : row.updatedBy(), row == null ? null : row.updatedAt());
    }

    private ModelAccessConfigView toView(EffectiveState state) {
        return new ModelAccessConfigView(state.provider(), state.modelName(), state.apiBaseUrl(),
                state.timeoutSeconds(), state.apiKeyConfigured(), ModelAccessConfigView.API_KEY_MASK,
                state.source(), state.updatedBy(), state.updatedAt());
    }

    private List<String> changedFields(EffectiveState before, EffectiveState after, boolean keySubmitted) {
        List<String> changed = new ArrayList<>();
        if (!Objects.equals(before.provider(), after.provider())) changed.add("provider");
        if (!Objects.equals(before.modelName(), after.modelName())) changed.add("modelName");
        if (!Objects.equals(before.apiBaseUrl(), after.apiBaseUrl())) changed.add("apiBaseUrl");
        if (Double.compare(before.timeoutSeconds(), after.timeoutSeconds()) != 0) changed.add("timeoutSeconds");
        if (keySubmitted && !Objects.equals(before.apiKeyFingerprint(), after.apiKeyFingerprint())) changed.add("apiKey");
        return List.copyOf(changed);
    }

    private void writeAudit(UUID accountId, List<String> changed, EffectiveState after, String fingerprint) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("changedFields", changed);
        payload.put("provider", after.provider());
        payload.put("model", after.modelName());
        payload.put("apiKeyChanged", changed.contains("apiKey"));
        payload.put("apiKeyFingerprint", fingerprint);
        try {
            jdbc.update("""
                    INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
                    VALUES (?, 'model.access.updated', 'model_access_config', 'global', ?::jsonb)
                    """, "account:" + accountId, objectMapper.writeValueAsString(payload));
        } catch (JsonProcessingException failure) {
            throw new IllegalStateException("unable to serialize model access audit", failure);
        }
    }

    private ApiException sealed(String message) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_CONFIG_SEALED", message);
    }
    private static boolean hasStoredKey(ModelAccessStore.StoredConfig row) {
        return row != null && row.apiKeyCiphertext() != null && row.apiKeyNonce() != null;
    }
    private static String choose(String stored, String fallback) { return stored == null || stored.isBlank() ? fallback : stored; }
    private static String fallback(String value, String fallback) { return value == null || value.isBlank() ? fallback : value; }
    private static double parseTimeout(String value) {
        try {
            double parsed = Double.parseDouble(value);
            return Double.isFinite(parsed) && parsed > 0 ? parsed : 45.0;
        } catch (RuntimeException ignored) { return 45.0; }
    }

    public record EffectiveConfig(String provider, String modelName, String apiBaseUrl,
            String apiKey, Double timeoutSeconds, String source) {}
    private record EffectiveState(String provider, String modelName, String apiBaseUrl,
            Double timeoutSeconds, boolean apiKeyConfigured, String apiKeyFingerprint,
            String source, String updatedBy, OffsetDateTime updatedAt) {}
}
