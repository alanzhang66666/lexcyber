package com.lexcyber.server.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.settings.ModelAccessAuthorization;
import com.lexcyber.server.settings.ModelAccessConfigView;
import com.lexcyber.server.settings.ModelAccessService;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;

@ExtendWith(MockitoExtension.class)
class ModelAccessControllerTest {
    private static final UUID ACCOUNT_ID = UUID.fromString("11111111-1111-4111-8111-111111111111");

    @Mock
    AuthService auth;
    @Mock
    ModelAccessAuthorization authorization;
    @Mock
    ModelAccessService models;

    @Test
    void modelAccessReadRequiresAdministrator() {
        AuthAccount account = new AuthAccount(ACCOUNT_ID, "alice", "Alice");
        when(auth.require("Bearer token")).thenReturn(account);
        ApiException denied = new ApiException(
                HttpStatus.FORBIDDEN, "MODEL_CONFIG_FORBIDDEN", "administrator required");
        doThrow(denied).when(authorization).requireAdministrator(account);

        ApiException actual = assertThrows(ApiException.class,
                () -> new ModelAccessController(auth, authorization, models).get("Bearer token"));

        assertEquals("MODEL_CONFIG_FORBIDDEN", actual.code());
        verify(models, org.mockito.Mockito.never()).get();
    }

    @Test
    void allowlistedAdministratorCanReadModelAccess() {
        AuthAccount account = new AuthAccount(ACCOUNT_ID, "admin", "Admin");
        ModelAccessConfigView view = new ModelAccessConfigView(
                "stub", "stub-general-v1", "https://api.example/v1", 45.0,
                false, ModelAccessConfigView.API_KEY_MASK, "environment", null,
                OffsetDateTime.parse("2026-09-30T00:00:00Z"));
        when(auth.require("Bearer token")).thenReturn(account);
        when(models.get()).thenReturn(view);

        assertEquals(view, new ModelAccessController(auth, authorization, models).get("Bearer token"));
        verify(authorization).requireAdministrator(account);
        verify(models).get();
    }
}
