package com.lexcyber.server.auth;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AuthLogin(
        @NotBlank @Size(max = 32) String username,
        @NotBlank @Size(min = 8, max = 128) String password) {
}
