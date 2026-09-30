package com.lexcyber.server.settings;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.auth.AuthAccount;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class ModelAccessAuthorizationTest {
    private static final UUID ACCOUNT_ID = UUID.fromString("11111111-1111-4111-8111-111111111111");

    @Test
    void onlyExplicitlyAllowlistedUsernameCanReadOrWriteDeploymentConfig() {
        ModelAccessAuthorization authorization = new ModelAccessAuthorization(" Admin,CONFIG-OWNER ");

        assertDoesNotThrow(() -> authorization.requireAdministrator(
                new AuthAccount(ACCOUNT_ID, "admin", "Admin")));
        assertDoesNotThrow(() -> authorization.requireAdministrator(
                new AuthAccount(ACCOUNT_ID, "config-owner", "Config Owner")));

        ApiException denied = assertThrows(ApiException.class, () -> authorization.requireAdministrator(
                new AuthAccount(ACCOUNT_ID, "alice", "Alice")));
        org.junit.jupiter.api.Assertions.assertEquals(HttpStatus.FORBIDDEN, denied.status());
        org.junit.jupiter.api.Assertions.assertEquals("MODEL_CONFIG_FORBIDDEN", denied.code());
    }

    @Test
    void emptyAllowlistDeniesEveryAccount() {
        ModelAccessAuthorization authorization = new ModelAccessAuthorization("");

        assertThrows(ApiException.class, () -> authorization.requireAdministrator(
                new AuthAccount(ACCOUNT_ID, "admin", "Admin")));
    }
}
