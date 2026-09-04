package com.lexcyber.server.review;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ReviewDecision(@NotNull @Min(1) Integer resultVersion, @Size(max = 5000) String comment) {
}
