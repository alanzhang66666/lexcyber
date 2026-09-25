package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.settings.ModelAccessConfigUpdate;
import com.lexcyber.server.settings.ModelAccessConfigView;
import com.lexcyber.server.settings.ModelAccessService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/settings/model-access")
public class ModelAccessController {
    private final AuthService auth;
    private final ModelAccessService models;

    public ModelAccessController(AuthService auth, ModelAccessService models) {
        this.auth = auth;
        this.models = models;
    }

    @GetMapping
    public ModelAccessConfigView get(@RequestHeader(value = "Authorization", required = false) String authorization) {
        auth.require(authorization);
        return models.get();
    }

    @PutMapping
    public ModelAccessConfigView put(@Valid @RequestBody ModelAccessConfigUpdate update,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return models.update(account.id(), update);
    }
}
