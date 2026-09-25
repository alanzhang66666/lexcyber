package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.SourceSearchRequest;
import com.lexcyber.server.domain.SourceSearchResponse;
import com.lexcyber.server.engine.EngineSourceClient;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SourceSearchController {
    private final AuthService auth;
    private final EngineSourceClient sources;

    public SourceSearchController(AuthService auth, EngineSourceClient sources) {
        this.auth = auth;
        this.sources = sources;
    }

    @PostMapping("/v1/sources/search")
    public SourceSearchResponse search(@Valid @RequestBody SourceSearchRequest request,
                                       @RequestHeader(value = "Authorization", required = false) String authorization) {
        auth.require(authorization);
        return sources.search(request);
    }
}
