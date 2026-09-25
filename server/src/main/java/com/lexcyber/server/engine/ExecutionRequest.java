package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;
import java.util.UUID;

/** Stable wire contract between the application boundary and the Python engine. */
public record ExecutionRequest(
        @JsonProperty("task_id") UUID taskId,
        @JsonProperty("execution_id") UUID executionId,
        @JsonProperty("request_id") UUID requestId,
        @JsonProperty("result_id") UUID resultId,
        @JsonProperty("result_version") int resultVersion,
        @JsonProperty("result_type") String resultType,
        String query,
        @JsonProperty("case_id") String caseId,
        @JsonProperty("session_id") String sessionId,
        Map<String, Object> metadata,
        @JsonProperty("input_hash") String inputHash,
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("artifact_stream_id") UUID artifactStreamId,
        @JsonProperty("input_snapshot_ref") String inputSnapshotRef) {
}
