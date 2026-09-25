package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.FactService;
import com.lexcyber.server.domain.FactUpdate;
import com.lexcyber.server.domain.FactView;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/cases/{caseId}/facts")
public class FactController {
    private final AuthService auth;
    private final FactService facts;

    public FactController(AuthService auth, FactService facts) {
        this.auth = auth;
        this.facts = facts;
    }

    @GetMapping
    public FactView get(@PathVariable String caseId,
                        @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return facts.get(account.id(), caseId);
    }

    @PutMapping
    public FactView put(@PathVariable String caseId,
                        @Valid @RequestBody FactUpdate update,
                        @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return facts.replace(account.id(), caseId, update);
    }

    @PostMapping("/confirm")
    public FactView confirm(@PathVariable String caseId,
                            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return facts.confirm(account.id(), caseId);
    }
}
