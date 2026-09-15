package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotNull;
import java.util.List;

public record FactUpdate(@NotNull List<FactItem> items) {
}
