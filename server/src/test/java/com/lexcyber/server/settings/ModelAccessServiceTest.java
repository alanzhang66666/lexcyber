package com.lexcyber.server.settings;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.api.ApiException;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;

class ModelAccessServiceTest {
    private static final UUID ACCOUNT_ID = UUID.fromString("11111111-1111-4111-8111-111111111111");
    private static final OffsetDateTime UPDATED_AT = OffsetDateTime.parse("2026-09-19T10:15:30Z");
    private static final String ENVIRONMENT_API_KEY = "environment-api-key-must-not-leak";
    private static final String STORED_API_KEY = "stored-api-key-must-not-leak";

    private final ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

    @Test
    void publicReadReturnsOnlyConfiguredFlagAndFixedMask() throws Exception {
        ModelAccessStore store = mock(ModelAccessStore.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(store.findGlobal()).thenReturn(Optional.empty());

        ModelAccessConfigView view = service(store, jdbc, new SecretBox("encryption-secret"),
                ENVIRONMENT_API_KEY).get();

        assertTrue(view.apiKeyConfigured());
        assertEquals(ModelAccessConfigView.API_KEY_MASK, view.apiKeyMask());
        assertEquals("environment", view.source());

        String serialized = objectMapper.writeValueAsString(view);
        assertFalse(serialized.contains(ENVIRONMENT_API_KEY));
        assertFalse(serialized.contains("\"apiKey\""));
        assertEquals("********", view.apiKeyMask());
    }

    @Test
    void publicReadMergesStoredAndEnvironmentFieldsAndReportsStoredSource() {
        ModelAccessStore store = mock(ModelAccessStore.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        byte[] ciphertext = {1, 2, 3};
        byte[] nonce = {4, 5, 6};
        ModelAccessStore.StoredConfig stored = row(
                "openai", "", "", ciphertext, nonce,
                ModelAccessStore.apiKeyFingerprint(STORED_API_KEY), null, "account:stored");
        when(store.findGlobal()).thenReturn(Optional.of(stored));

        ModelAccessConfigView view = service(store, jdbc, new SecretBox("encryption-secret"), "").get();

        assertEquals("openai", view.provider());
        assertEquals("environment-model", view.modelName());
        assertEquals("https://environment.example/v1", view.apiBaseUrl());
        assertEquals(17.5, view.timeoutSeconds());
        assertTrue(view.apiKeyConfigured());
        assertEquals("stored", view.source());
        assertEquals("account:stored", view.updatedBy());
        assertEquals(UPDATED_AT, view.updatedAt());
    }

    @Test
    void updateWithOmittedKeyPreservesItAndEmptyKeyClearsIt() {
        ModelAccessStore store = mock(ModelAccessStore.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        SecretBox box = new SecretBox("encryption-secret");
        SecretBox.Sealed sealed = box.seal(STORED_API_KEY);
        ModelAccessStore.StoredConfig before = row(
                "openai", "stored-model", "https://stored.example/v1",
                sealed.ciphertext(), sealed.nonce(),
                ModelAccessStore.apiKeyFingerprint(STORED_API_KEY), 22.0, "account:old");
        ModelAccessStore.StoredConfig afterClear = row(
                "openai", "stored-model", "https://stored.example/v1",
                null, null, null, 22.0, "account:new");
        when(store.findGlobal()).thenReturn(Optional.of(before));

        ModelAccessConfigUpdate keep = update(null);
        ModelAccessConfigUpdate clear = update("");
        when(store.upsert(eq(keep), any(byte[].class), any(byte[].class), eq(ACCOUNT_ID.toString())))
                .thenReturn(before);
        when(store.upsert(eq(clear), isNull(byte[].class), isNull(byte[].class), eq(ACCOUNT_ID.toString())))
                .thenReturn(afterClear);

        ModelAccessService modelAccess = service(store, jdbc, box, "");
        ModelAccessConfigView kept = modelAccess.update(ACCOUNT_ID, keep);
        ModelAccessConfigView cleared = modelAccess.update(ACCOUNT_ID, clear);

        assertTrue(kept.apiKeyConfigured());
        assertFalse(cleared.apiKeyConfigured());

        ArgumentCaptor<byte[]> ciphertextCaptor = ArgumentCaptor.forClass(byte[].class);
        ArgumentCaptor<byte[]> nonceCaptor = ArgumentCaptor.forClass(byte[].class);
        verify(store).upsert(eq(keep), ciphertextCaptor.capture(), nonceCaptor.capture(), eq(ACCOUNT_ID.toString()));
        assertArrayEquals(sealed.ciphertext(), ciphertextCaptor.getValue());
        assertArrayEquals(sealed.nonce(), nonceCaptor.getValue());
        verify(store).upsert(eq(clear), isNull(byte[].class), isNull(byte[].class), eq(ACCOUNT_ID.toString()));
    }

    @Test
    void updateWithNonEmptyKeySealsItBeforeCallingStore() {
        ModelAccessStore store = mock(ModelAccessStore.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        SecretBox box = new SecretBox("encryption-secret");
        String newKey = "new-api-key-must-not-leak";
        ModelAccessConfigUpdate update = update(newKey);
        doAnswer(invocation -> {
            byte[] ciphertext = invocation.getArgument(1, byte[].class);
            byte[] nonce = invocation.getArgument(2, byte[].class);
            return row(
                    update.provider(), update.modelName(), update.apiBaseUrl(),
                    ciphertext, nonce, ModelAccessStore.apiKeyFingerprint(newKey),
                    update.timeoutSeconds(), "account:" + ACCOUNT_ID);
        }).when(store).upsert(eq(update), any(byte[].class), any(byte[].class), eq(ACCOUNT_ID.toString()));
        when(store.findGlobal()).thenReturn(Optional.empty());

        ModelAccessConfigView view = service(store, jdbc, box, "").update(ACCOUNT_ID, update);

        ArgumentCaptor<byte[]> ciphertextCaptor = ArgumentCaptor.forClass(byte[].class);
        ArgumentCaptor<byte[]> nonceCaptor = ArgumentCaptor.forClass(byte[].class);
        verify(store).upsert(eq(update), ciphertextCaptor.capture(), nonceCaptor.capture(), eq(ACCOUNT_ID.toString()));
        assertNotNull(ciphertextCaptor.getValue());
        assertNotNull(nonceCaptor.getValue());
        assertEquals(newKey, box.open(ciphertextCaptor.getValue(), nonceCaptor.getValue()));
        assertFalse(Arrays.equals(
                newKey.getBytes(StandardCharsets.UTF_8), ciphertextCaptor.getValue()));
        assertTrue(view.apiKeyConfigured());
    }

    @Test
    void updateAuditsExactChangedFieldsWithoutWritingApiKeyPlaintext() throws Exception {
        ModelAccessStore store = mock(ModelAccessStore.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        SecretBox box = new SecretBox("encryption-secret");
        SecretBox.Sealed oldKey = box.seal("old-api-key");
        String newKey = "new-api-key-must-not-leak";
        ModelAccessStore.StoredConfig before = row(
                "stub", "old-model", "https://old.example/v1",
                oldKey.ciphertext(), oldKey.nonce(),
                ModelAccessStore.apiKeyFingerprint("old-api-key"), 10.0, "account:old");
        ModelAccessConfigUpdate update = new ModelAccessConfigUpdate(
                "openai", "new-model", "https://new.example/v1", newKey, 30.0);
        doAnswer(invocation -> {
            byte[] ciphertext = invocation.getArgument(1, byte[].class);
            byte[] nonce = invocation.getArgument(2, byte[].class);
            return row(
                    update.provider(), update.modelName(), update.apiBaseUrl(),
                    ciphertext, nonce, ModelAccessStore.apiKeyFingerprint(newKey),
                    update.timeoutSeconds(), "account:" + ACCOUNT_ID);
        }).when(store).upsert(eq(update), any(byte[].class), any(byte[].class), eq(ACCOUNT_ID.toString()));
        when(store.findGlobal()).thenReturn(Optional.of(before));

        service(store, jdbc, box, "").update(ACCOUNT_ID, update);

        String auditJson = capturedAuditPayload(jdbc);
        JsonNode audit = objectMapper.readTree(auditJson);
        assertEquals(
                objectMapper.readTree("[\"provider\",\"modelName\",\"apiBaseUrl\",\"apiKey\",\"timeoutSeconds\"]"),
                audit.get("changedFields"));
        assertTrue(audit.get("apiKeyChanged").asBoolean());
        assertEquals(ModelAccessStore.apiKeyFingerprint(newKey), audit.get("apiKeyFingerprint").asText());
        assertFalse(audit.has("apiKey"));
        assertFalse(auditJson.contains(newKey));
    }

    @Test
    void sealedConfigurationRejectsNonEmptyApiKeyWithoutCallingStore() {
        ModelAccessStore store = mock(ModelAccessStore.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(store.findGlobal()).thenReturn(Optional.empty());
        String plaintext = "sealed-api-key-must-not-leak";

        ApiException error = assertThrows(ApiException.class,
                () -> service(store, jdbc, new SecretBox(""), "")
                        .update(ACCOUNT_ID, update(plaintext)));

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, error.status());
        assertEquals("MODEL_CONFIG_SEALED", error.code());
        assertFalse(error.getMessage().contains(plaintext));
        verify(store, never()).upsert(
                any(ModelAccessConfigUpdate.class), any(byte[].class), any(byte[].class), anyString());
    }

    private ModelAccessService service(ModelAccessStore store, JdbcTemplate jdbc, SecretBox box,
                                       String environmentApiKey) {
        return new ModelAccessService(
                store,
                jdbc,
                objectMapper,
                box,
                "environment-provider",
                "environment-model",
                "https://environment.example/v1",
                environmentApiKey,
                17.5);
    }

    private ModelAccessConfigUpdate update(String apiKey) {
        return new ModelAccessConfigUpdate(
                "openai", "stored-model", "https://stored.example/v1", apiKey, 22.0);
    }

    private ModelAccessStore.StoredConfig row(
            String provider,
            String modelName,
            String apiBaseUrl,
            byte[] ciphertext,
            byte[] nonce,
            String fingerprint,
            Double timeoutSeconds,
            String updatedBy) {
        return new ModelAccessStore.StoredConfig(
                ModelAccessStore.GLOBAL_SCOPE,
                provider,
                modelName,
                apiBaseUrl,
                ciphertext,
                nonce,
                fingerprint,
                timeoutSeconds,
                updatedBy,
                UPDATED_AT);
    }

    private String capturedAuditPayload(JdbcTemplate jdbc) {
        ArgumentCaptor<String> payloadCaptor = ArgumentCaptor.forClass(String.class);
        verify(jdbc).update(anyString(), eq("account:" + ACCOUNT_ID), payloadCaptor.capture());
        return payloadCaptor.getValue();
    }
}
