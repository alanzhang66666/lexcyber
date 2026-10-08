package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.CaseAnalysisDateUpdate;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v2/cases")
public class CaseAnalysisController {
    private final AuthService auth;
    private final CaseService cases;

    public CaseAnalysisController(AuthService auth, CaseService cases) {
        this.auth = auth;
        this.cases = cases;
    }

    @PutMapping("/{caseId}/analysis-date")
    public CaseView updateDate(@PathVariable String caseId,
            @Valid @RequestBody CaseAnalysisDateUpdate request,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        return cases.updateAnalysisDate(auth.require(authorization).id(), caseId, request);
    }
}
