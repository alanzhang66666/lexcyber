package com.lexcyber.server.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.DraftExportService;
import com.lexcyber.server.domain.V2LifecycleService;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

@ExtendWith(MockitoExtension.class)
class DraftExportControllerTest {
    private static final String DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private final AuthAccount owner = new AuthAccount(UUID.randomUUID(), "alice", "Alice");
    private final UUID artifact = UUID.randomUUID();
    private final String caseId = UUID.randomUUID().toString();
    @Mock AuthService auth;
    @Mock V2LifecycleService lifecycle;
    @Mock DraftExportService exports;
    private MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders.standaloneSetup(new V2LifecycleController(lifecycle, auth, exports))
                .setControllerAdvice(new ApiExceptionHandler()).build();
    }

    @ParameterizedTest
    @EnumSource(value = HttpStatus.class, names = {"NOT_FOUND", "CONFLICT", "SERVICE_UNAVAILABLE"})
    void returnsStructuredErrorsEvenWhenOnlyDocxIsAccepted(HttpStatus errorStatus) throws Exception {
        when(auth.require("Bearer token")).thenReturn(owner);
        when(exports.export(owner.id(), caseId, artifact))
                .thenThrow(new ApiException(errorStatus, "EXPORT_TEST_ERROR", "导出失败"));
        mvc.perform(get(path()).header("Authorization", "Bearer token").accept(DOCX))
                .andExpect(status().is(errorStatus.value()))
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value("EXPORT_TEST_ERROR"))
                .andExpect(jsonPath("$.traceId").isString())
                .andExpect(header().doesNotExist("Content-Disposition"));
    }

    @Test
    void unauthenticatedDownloadReturnsJson401WithDocxAccept() throws Exception {
        when(auth.require(any())).thenThrow(new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "需要会话"));
        mvc.perform(get(path()).accept(DOCX))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void successfulDownloadRetainsBinaryHeadersAndExactVersion() throws Exception {
        when(auth.require("Bearer token")).thenReturn(owner);
        byte[] bytes = {'P', 'K', 3, 4};
        when(exports.export(owner.id(), caseId, artifact)).thenReturn(
                new DraftExportService.ExportedDocx(bytes, "文书-v2.docx", "hash", artifact, 2));
        mvc.perform(get(path()).header("Authorization", "Bearer token").accept(DOCX))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(DOCX))
                .andExpect(content().bytes(bytes))
                .andExpect(header().string("X-Artifact-Version-Id", artifact.toString()))
                .andExpect(header().string("Cache-Control", "private, no-store"));
    }

    private String path() {
        return "/v2/cases/" + caseId + "/artifact-versions/" + artifact + "/export.docx";
    }
}
