package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.V2LifecycleService;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** contracts/public-api-v2.yaml — 生命周期语义端点（facts/module/artifact/review/archive）。 */
@RestController
@RequestMapping("/v2")
public class V2LifecycleController {
    private final V2LifecycleService lifecycle;
    private final AuthService auth;

    public V2LifecycleController(V2LifecycleService lifecycle, AuthService auth) {
        this.lifecycle = lifecycle;
        this.auth = auth;
    }

    @PostMapping("/cases/{caseId}/facts-versions")
    public ResponseEntity<Map<String, Object>> createFactsVersion(@PathVariable String caseId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(lifecycle.createFactsVersion(account.id(), caseId));
    }

    @PostMapping("/cases/{caseId}/facts-versions/{factsVersionId}/confirm")
    public Map<String, Object> confirmFactsVersion(@PathVariable String caseId,
            @PathVariable UUID factsVersionId,
            @RequestBody(required = false) Map<String, Object> body,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        UUID expected = parseUuid(body == null ? null : body.get("expectedConfirmedFactsVersionId"));
        return lifecycle.confirmFactsVersion(account.id(), caseId, factsVersionId, expected);
    }

    @GetMapping("/cases/{caseId}/facts-versions")
    public Map<String, Object> listFactsVersions(@PathVariable String caseId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return Map.of("items", lifecycle.listFactsVersions(account.id(), caseId));
    }

    @GetMapping("/cases/{caseId}/facts-versions/{factsVersionId}")
    public Map<String, Object> factsVersionDetail(@PathVariable String caseId,
            @PathVariable UUID factsVersionId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.factsVersionDetail(account.id(), caseId, factsVersionId);
    }

    @GetMapping("/cases/{caseId}/facts-versions/{factsVersionId}/diff")
    public Map<String, Object> factsVersionDiff(@PathVariable String caseId,
            @PathVariable UUID factsVersionId,
            @RequestParam("against") UUID against,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.factsVersionDiff(account.id(), caseId, against, factsVersionId);
    }

    @PostMapping("/cases/{caseId}/facts-versions/{factsVersionId}/clone")
    public Map<String, Object> cloneFactsVersion(@PathVariable String caseId,
            @PathVariable UUID factsVersionId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.cloneFactsVersion(account.id(), caseId, factsVersionId);
    }

    @GetMapping("/cases/{caseId}/facts-entities")
    public Map<String, Object> factsEntities(@PathVariable String caseId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.factsEntities(account.id(), caseId);
    }

    @PutMapping("/cases/{caseId}/facts-entities/{kind}")
    public Map<String, Object> replaceFactsEntities(@PathVariable String caseId,
            @PathVariable String kind,
            @RequestBody(required = false) Map<String, Object> body,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.replaceFactsEntities(account.id(), caseId, kind, body);
    }

    @GetMapping("/cases/{caseId}/facts-head")
    public Map<String, Object> factsHead(@PathVariable String caseId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.factsHead(account.id(), caseId);
    }

    @PostMapping("/cases/{caseId}/modules/{module}/executions")
    public Map<String, Object> dispatchModuleExecution(@PathVariable String caseId,
            @PathVariable String module,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.dispatchModuleExecution(account.id(), caseId, module);
    }

    @GetMapping("/executions/{executionId}")
    public Map<String, Object> execution(@PathVariable UUID executionId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.execution(account.id(), executionId);
    }

    @GetMapping("/artifact-versions/{artifactVersionId}")
    public Map<String, Object> artifactVersion(@PathVariable UUID artifactVersionId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.artifactVersion(account.id(), artifactVersionId);
    }

    @GetMapping("/cases/{caseId}/modules/{module}")
    public Map<String, Object> moduleHead(@PathVariable String caseId, @PathVariable String module,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.moduleHead(account.id(), caseId, module);
    }

    @PostMapping("/artifact-versions/{artifactVersionId}/reviews")
    public ResponseEntity<Map<String, Object>> openReview(@PathVariable UUID artifactVersionId,
            @RequestBody(required = false) Map<String, Object> body,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        String comment = body == null ? null
                : (body.get("comment") == null ? null : String.valueOf(body.get("comment")));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(lifecycle.openReview(account.id(), artifactVersionId, comment));
    }

    @GetMapping("/artifact-versions/{artifactVersionId}/reviews")
    public Map<String, Object> listReviews(@PathVariable UUID artifactVersionId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.listReviews(account.id(), artifactVersionId);
    }

    @PostMapping("/cases/{caseId}/drafts/render")
    public Map<String, Object> dispatchDraftRender(@PathVariable String caseId,
            @RequestBody(required = false) Map<String, Object> body,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        String docType = body == null ? null
                : (body.get("docType") == null ? null : String.valueOf(body.get("docType")));
        return lifecycle.dispatchDraftRender(account.id(), caseId, docType);
    }

    @GetMapping("/cases/{caseId}/drafts")
    public Map<String, Object> listDraftStreams(@PathVariable String caseId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.listDraftStreams(account.id(), caseId);
    }

    @GetMapping("/drafts/{draftId}")
    public Map<String, Object> draftHead(@PathVariable String draftId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.draftHead(account.id(), draftId);
    }

    @PostMapping("/cases/{caseId}/archives")
    public ResponseEntity<Map<String, Object>> createArchive(@PathVariable String caseId,
            @RequestBody(required = false) Map<String, Object> body,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        String profile = body == null ? null
                : (body.get("archiveProfile") == null ? null : String.valueOf(body.get("archiveProfile")));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(lifecycle.createArchive(account.id(), caseId, profile));
    }

    @GetMapping("/cases/{caseId}/archives/{archiveId}")
    public Map<String, Object> archive(@PathVariable String caseId, @PathVariable UUID archiveId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return lifecycle.archive(account.id(), caseId, archiveId);
    }

    private static UUID parseUuid(Object raw) {
        if (raw == null) {
            return null;
        }
        try {
            return UUID.fromString(String.valueOf(raw));
        } catch (IllegalArgumentException ex) {
            throw new com.lexcyber.server.api.ApiException(HttpStatus.BAD_REQUEST,
                    "INVALID_REQUEST", "expectedConfirmedFactsVersionId must be a uuid");
        }
    }
}
