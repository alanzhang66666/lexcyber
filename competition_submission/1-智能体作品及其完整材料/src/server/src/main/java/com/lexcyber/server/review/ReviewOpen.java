package com.lexcyber.server.review;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record ReviewOpen(
        @NotBlank String module,
        String draftId,
        Integer draftVersion,
        String moduleState,
        Integer moduleVersion,
        Integer resultVersion,
        UUID taskId,
        @Size(max = 500) String returnTarget) {
}
