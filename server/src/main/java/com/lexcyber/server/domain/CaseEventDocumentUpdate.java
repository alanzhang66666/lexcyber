package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotBlank;

/** Bind an existing relation event to the ID returned by a case document upload. */
public record CaseEventDocumentUpdate(@NotBlank String documentId, String locator) {
}
