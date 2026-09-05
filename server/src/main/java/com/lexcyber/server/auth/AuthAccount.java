package com.lexcyber.server.auth;

import java.util.UUID;

public record AuthAccount(UUID id, String username, String displayName) {
}
