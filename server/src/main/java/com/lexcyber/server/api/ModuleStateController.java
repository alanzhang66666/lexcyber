package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.ModulePolicies;
import com.lexcyber.server.domain.ModuleStateService;
import com.lexcyber.server.domain.ModuleStateUpdate;
import com.lexcyber.server.domain.ModuleStateView;
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
@RequestMapping("/v1/cases/{caseId}")
public class ModuleStateController {
    private final AuthService auth;
    private final ModuleStateService modules;

    public ModuleStateController(AuthService auth, ModuleStateService modules) {
        this.auth = auth;
        this.modules = modules;
    }

    @GetMapping("/compliance")
    public ModuleStateView getCompliance(@PathVariable String caseId,
                                         @RequestHeader(value = "Authorization", required = false) String authorization) {
        return get(caseId, ModulePolicies.COMPLIANCE, authorization);
    }

    @PutMapping("/compliance")
    public ModuleStateView putCompliance(@PathVariable String caseId,
                                         @Valid @RequestBody ModuleStateUpdate update,
                                         @RequestHeader(value = "Authorization", required = false) String authorization) {
        return replace(caseId, ModulePolicies.COMPLIANCE, update, authorization);
    }

    @PostMapping("/compliance/confirm")
    public ModuleStateView confirmCompliance(@PathVariable String caseId,
                                             @RequestHeader(value = "Authorization", required = false) String authorization) {
        return confirm(caseId, ModulePolicies.COMPLIANCE, authorization);
    }

    @GetMapping("/conviction")
    public ModuleStateView getConviction(@PathVariable String caseId,
                                         @RequestHeader(value = "Authorization", required = false) String authorization) {
        return get(caseId, ModulePolicies.CONVICTION, authorization);
    }

    @PutMapping("/conviction")
    public ModuleStateView putConviction(@PathVariable String caseId,
                                         @Valid @RequestBody ModuleStateUpdate update,
                                         @RequestHeader(value = "Authorization", required = false) String authorization) {
        return replace(caseId, ModulePolicies.CONVICTION, update, authorization);
    }

    @PostMapping("/conviction/confirm")
    public ModuleStateView confirmConviction(@PathVariable String caseId,
                                             @RequestHeader(value = "Authorization", required = false) String authorization) {
        return confirm(caseId, ModulePolicies.CONVICTION, authorization);
    }

    private ModuleStateView get(String caseId, String module, String authorization) {
        AuthAccount account = auth.require(authorization);
        return modules.get(account.id(), caseId, module);
    }

    private ModuleStateView replace(String caseId, String module, ModuleStateUpdate update, String authorization) {
        AuthAccount account = auth.require(authorization);
        return modules.replace(account.id(), caseId, module, update);
    }

    private ModuleStateView confirm(String caseId, String module, String authorization) {
        AuthAccount account = auth.require(authorization);
        return modules.confirm(account.id(), caseId, module);
    }
}
