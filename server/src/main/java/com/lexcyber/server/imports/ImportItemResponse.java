package com.lexcyber.server.imports;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public record ImportItemResponse(
        UUID id,
        int ordinal,
        String itemId,
        String externalCaseId,
        String status,
        String caseId,
        String payloadPath,
        String payloadSha256,
        Map<String, Object> diff,
        Map<String, Object> error,
        List<ImportStepResponse> steps,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime completedAt) {

    public static ImportItemResponse from(ImportItemView value, List<ImportStepView> steps) {
        return new ImportItemResponse(
                value.id(), value.ordinal(), value.itemId(), value.externalCaseId(),
                value.status(), value.caseId(), value.payloadPath(), value.payloadSha256(),
                value.diff(), value.error(), steps.stream().map(ImportStepResponse::from).toList(),
                value.createdAt(), value.updatedAt(), value.completedAt());
    }
}
