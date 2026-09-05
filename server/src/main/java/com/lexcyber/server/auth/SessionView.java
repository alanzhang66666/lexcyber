package com.lexcyber.server.auth;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.OffsetDateTime;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record SessionView(String token, String username, String displayName, OffsetDateTime expiresAt) {
}
