package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.CaseCreate;
import com.lexcyber.server.domain.CaseEventDocumentUpdate;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
import com.lexcyber.server.domain.PageResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/cases")
public class CaseController {
    private final AuthService auth;
    private final CaseService cases;

    public CaseController(AuthService auth, CaseService cases) {
        this.auth = auth;
        this.cases = cases;
    }

    @PostMapping
    public ResponseEntity<CaseView> create(@Valid @RequestBody CaseCreate request,
                                           @RequestHeader(value = "Authorization", required = false) String authorization,
                                           @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        AuthAccount account = auth.require(authorization);
        CaseView created = idempotencyKey == null
                ? cases.create(account.id(), request)
                : cases.create(account.id(), request, idempotencyKey);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping
    public PageResponse<CaseView> list(@RequestParam(defaultValue = "0") int page,
                                       @RequestParam(defaultValue = "20") int size,
                                       @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return cases.list(account.id(), page, size);
    }

    @GetMapping("/{caseId}")
    public CaseView get(@PathVariable String caseId,
                        @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return cases.requireOwned(account.id(), caseId);
    }

    @PatchMapping("/{caseId}/metadata/relations/events/{eventId}/document")
    public CaseView bindEventDocument(@PathVariable String caseId,
                                      @PathVariable String eventId,
                                      @Valid @RequestBody CaseEventDocumentUpdate request,
                                      @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return cases.bindEventDocument(account.id(), caseId, eventId, request);
    }
}
