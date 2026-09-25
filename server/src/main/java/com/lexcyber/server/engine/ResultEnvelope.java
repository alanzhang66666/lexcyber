package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;
import java.util.UUID;

/** Terminal execution payload shared by callback and reconciliation polling. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ResultEnvelope(
        @JsonProperty("execution_id") UUID executionId,
        @JsonProperty("task_id") UUID taskId,
        @JsonProperty("request_id") UUID requestId,
        @JsonProperty("result_id") UUID resultId,
        @JsonProperty("result_version") int resultVersion,
        @JsonProperty("result_type") String resultType,
        String status,
        @JsonProperty("current_stage") String currentStage,
        @JsonProperty("content_json") String contentJson,
        @JsonProperty("content_hash") String contentHash,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("error_message") String errorMessage,
        boolean retryable,
        @JsonProperty("result_ref")
        Map<String, Object> resultRef,
        @JsonProperty("fencing_token") Long fencingToken,
        @JsonProperty("completion_identity") String completionIdentity,
        @JsonProperty("output_envelope") Map<String, Object> outputEnvelope) {
}
