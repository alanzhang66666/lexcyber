package com.lexcyber.server.settings;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.auth.AuthAccount;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * Authorization for deployment-wide model settings.
 *
 * <p>Model settings affect every task, so a normal authenticated session is
 * not sufficient. Until account roles are persisted, the deployment must
 * provide an explicit, comma-separated username allowlist.</p>
 */
@Component
public final class ModelAccessAuthorization {
    private final Set<String> administratorUsernames;

    public ModelAccessAuthorization(
            @Value("${MODEL_CONFIG_ADMIN_USERNAMES:}") String configuredUsernames) {
        this.administratorUsernames = parseUsernames(configuredUsernames);
    }

    public void requireAdministrator(AuthAccount account) {
        if (account == null || !administratorUsernames.contains(normalize(account.username()))) {
            throw new ApiException(
                    HttpStatus.FORBIDDEN,
                    "MODEL_CONFIG_FORBIDDEN",
                    "model access configuration requires an administrator account");
        }
    }

    static Set<String> parseUsernames(String configuredUsernames) {
        if (configuredUsernames == null || configuredUsernames.isBlank()) {
            return Set.of();
        }
        return Arrays.stream(configuredUsernames.split(","))
                .map(ModelAccessAuthorization::normalize)
                .filter(value -> !value.isBlank())
                .collect(Collectors.toUnmodifiableSet());
    }

    private static String normalize(String username) {
        return username == null ? "" : username.trim().toLowerCase(Locale.ROOT);
    }
}
