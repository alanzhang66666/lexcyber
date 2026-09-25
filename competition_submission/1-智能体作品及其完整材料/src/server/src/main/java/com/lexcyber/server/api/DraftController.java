package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.DraftCreate;
import com.lexcyber.server.domain.DraftList;
import com.lexcyber.server.domain.DraftService;
import com.lexcyber.server.domain.DraftUpdate;
import com.lexcyber.server.domain.DraftView;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/cases/{caseId}/drafts")
public class DraftController {
    private final AuthService auth;
    private final DraftService drafts;

    public DraftController(AuthService auth, DraftService drafts) {
        this.auth = auth;
        this.drafts = drafts;
    }

    @PostMapping
    public ResponseEntity<DraftView> create(@PathVariable String caseId,
                                            @Valid @RequestBody DraftCreate request,
                                            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ResponseEntity.status(HttpStatus.CREATED).body(drafts.create(account.id(), caseId, request));
    }

    @GetMapping
    public DraftList list(@PathVariable String caseId,
                          @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return drafts.list(account.id(), caseId);
    }

    @GetMapping("/{draftId}")
    public DraftView get(@PathVariable String caseId,
                         @PathVariable String draftId,
                         @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return drafts.get(account.id(), caseId, draftId);
    }

    @PutMapping("/{draftId}")
    public DraftView replace(@PathVariable String caseId,
                             @PathVariable String draftId,
                             @Valid @RequestBody DraftUpdate request,
                             @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return drafts.replace(account.id(), caseId, draftId, request);
    }
}
