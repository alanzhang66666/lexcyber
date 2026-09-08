package com.lexcyber.server.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.CaseView;
import com.lexcyber.server.domain.DocumentService;
import com.lexcyber.server.domain.DocumentView;
import com.lexcyber.server.domain.FactItem;
import com.lexcyber.server.domain.FactService;
import com.lexcyber.server.domain.FactView;
import com.lexcyber.server.domain.PageResponse;
import com.lexcyber.server.domain.SourceSearchRequest;
import com.lexcyber.server.domain.TaskService;
import com.lexcyber.server.domain.TaskView;
import com.lexcyber.server.engine.EngineSourceClient;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.server.ResponseStatusException;

@ExtendWith(MockitoExtension.class)
class CaseDocumentControllerTest {
    @Mock
    AuthService auth;
    @Mock
    CaseService cases;
    @Mock
    DocumentService documents;
    @Mock
    TaskService tasks;
    @Mock
    FactService facts;
    @Mock
    EngineSourceClient sources;
    MockMvc mvc;

    private final AuthAccount owner = new AuthAccount(UUID.randomUUID(), "alice", "Alice");

    @BeforeEach
    void setup() {
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        mvc = MockMvcBuilders.standaloneSetup(
                        new CaseController(auth, cases),
                        new DocumentController(auth, documents),
                        new TaskController(tasks, auth, cases, false),
                        new FactController(auth, facts),
                        new SourceSearchController(auth, sources))
                .setControllerAdvice(new ApiExceptionHandler())
                .setValidator(validator)
                .setMessageConverters(new MappingJackson2HttpMessageConverter(mapper))
                .build();
    }

    @Test
    void casesRequireBearer() throws Exception {
        when(auth.require(isNull())).thenThrow(new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session required"));
        mvc.perform(post("/v1/cases").contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"x\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
        mvc.perform(get("/v1/cases")).andExpect(status().isUnauthorized());
    }

    @Test
    void createsAndListsOwnedCases() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        CaseView view = new CaseView("case-demo-001", "测试案例 001", "CN", LocalDate.parse("2026-09-06"),
                Map.of("datasetCaseNo", "001"), OffsetDateTime.parse("2026-09-06T10:00:00Z"), OffsetDateTime.parse("2026-09-06T10:00:00Z"));
        when(cases.create(eq(owner.id()), any())).thenReturn(view);
        when(cases.list(eq(owner.id()), eq(0), eq(20))).thenReturn(new PageResponse<>(List.of(view), 0, 20, 1));
        when(cases.requireOwned(owner.id(), "case-demo-001")).thenReturn(view);

        mvc.perform(post("/v1/cases").header("Authorization", "Bearer token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"测试案例 001\",\"jurisdiction\":\"CN\",\"asOfDate\":\"2026-09-06\",\"metadata\":{\"datasetCaseNo\":\"001\"}}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("case-demo-001"))
                .andExpect(jsonPath("$.asOfDate").value("2026-09-06"));

        mvc.perform(get("/v1/cases?page=0&size=20").header("Authorization", "Bearer token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value("case-demo-001"))
                .andExpect(jsonPath("$.page").value(0))
                .andExpect(jsonPath("$.total").value(1));

        mvc.perform(get("/v1/cases/case-demo-001").header("Authorization", "Bearer token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("测试案例 001"));
    }

    @Test
    void crossUserCaseIs404() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        when(cases.requireOwned(owner.id(), "case-other")).thenThrow(new ApiException(HttpStatus.NOT_FOUND, "CASE_NOT_FOUND", "案件不存在或不可访问"));
        mvc.perform(get("/v1/cases/case-other").header("Authorization", "Bearer token"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CASE_NOT_FOUND"));
    }

    @Test
    void uploadCreatesParseTaskAndRejectsUnsupportedType() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        DocumentView uploaded = new DocumentView("doc-demo-001", "case-demo-001", "案情材料.docx",
                DocumentViewContent.DOCX, 18324, "input", "queued", UUID.fromString("33333333-3333-4333-8333-333333333333"),
                OffsetDateTime.parse("2026-09-06T10:01:00Z"));
        when(documents.upload(eq(owner.id()), eq("case-demo-001"), any(), any(), any(), eq("input"), eq("upload-demo-001")))
                .thenReturn(uploaded);
        when(documents.upload(eq(owner.id()), eq("case-demo-001"), any(), any(), any(), eq("input"), isNull()))
                .thenThrow(new ApiException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_DOCUMENT_TYPE", "仅支持 PDF 或 DOCX 材料"));

        mvc.perform(multipart("/v1/cases/case-demo-001/documents")
                        .file(new MockMultipartFile("file", "案情材料.docx", DocumentViewContent.DOCX, "docx".getBytes()))
                        .param("role", "input")
                        .header("Authorization", "Bearer token")
                        .header("Idempotency-Key", "upload-demo-001"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.parseTaskId").value("33333333-3333-4333-8333-333333333333"))
                .andExpect(jsonPath("$.parseStatus").value("queued"))
                .andExpect(jsonPath("$.role").value("input"));

        mvc.perform(multipart("/v1/cases/case-demo-001/documents")
                        .file(new MockMultipartFile("file", "notes.txt", "text/plain", "nope".getBytes()))
                        .param("role", "input")
                        .header("Authorization", "Bearer token"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_DOCUMENT_TYPE"));
    }

    @Test
    void documentAndCaseScopedTaskRequireOwnership() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        when(documents.requireOwned(owner.id(), "doc-hidden"))
                .thenThrow(new ApiException(HttpStatus.NOT_FOUND, "DOCUMENT_NOT_FOUND", "材料不存在或不可访问"));
        mvc.perform(get("/v1/documents/doc-hidden").header("Authorization", "Bearer token"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("DOCUMENT_NOT_FOUND"));

        UUID taskId = UUID.randomUUID();
        TaskView view = new TaskView(taskId, UUID.randomUUID(), UUID.randomUUID(), "case-demo-001",
                "queued", "accepted", null, null, null, OffsetDateTime.now(), OffsetDateTime.now());
        when(tasks.find(taskId)).thenReturn(Optional.of(view));
        when(cases.requireOwned(owner.id(), "case-demo-001"))
                .thenThrow(new ApiException(HttpStatus.NOT_FOUND, "CASE_NOT_FOUND", "案件不存在或不可访问"));
        mvc.perform(get("/v1/tasks/" + taskId).header("Authorization", "Bearer token"))
                .andExpect(status().isNotFound());
    }

    @Test
    void stubTasksWithoutCaseStayPublic() throws Exception {
        UUID taskId = UUID.randomUUID();
        TaskView view = new TaskView(taskId, UUID.randomUUID(), UUID.randomUUID(), "",
                "queued", "accepted", null, null, null, OffsetDateTime.now(), OffsetDateTime.now());
        when(tasks.find(taskId)).thenReturn(Optional.of(view));
        mvc.perform(get("/v1/tasks/" + taskId)).andExpect(status().isOk());
    }

    @Test
    void sentencingAndUnknownTaskTypesAreRejected() throws Exception {
        mvc.perform(post("/v1/tasks").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"q\",\"metadata\":{\"taskType\":\"sentencing.calculate\"}}"))
                .andExpect(status().isNotImplemented())
                .andExpect(jsonPath("$.code").value("SENTENCING_UNAVAILABLE"))
                .andExpect(jsonPath("$.retryable").value(false));
        mvc.perform(post("/v1/tasks").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"q\",\"metadata\":{\"taskType\":\"nope\"}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_TASK_TYPE"));
    }

    @Test
    void factsRequireOwnerAndReturnDraft() throws Exception {
        when(auth.require(isNull())).thenThrow(new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session required"));
        mvc.perform(get("/v1/cases/case-demo-001/facts"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));

        when(auth.require(any())).thenReturn(owner);
        when(facts.get(owner.id(), "case-demo-001")).thenReturn(new FactView(
                "case-demo-001", "case.facts.v1", "draft",
                List.of(new FactItem("f1", "amount", "100", "paragraph:1", "doc-1")),
                OffsetDateTime.parse("2026-09-08T10:00:00Z"), null));
        mvc.perform(get("/v1/cases/case-demo-001/facts").header("Authorization", "Bearer token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("draft"))
                .andExpect(jsonPath("$.items[0].key").value("amount"));

        when(facts.get(owner.id(), "hidden")).thenThrow(new ApiException(HttpStatus.NOT_FOUND, "CASE_NOT_FOUND", "案件不存在或不可访问"));
        mvc.perform(get("/v1/cases/hidden/facts").header("Authorization", "Bearer token"))
                .andExpect(status().isNotFound());
    }

    @Test
    void sourceSearchIsUnavailableWithoutCorpus() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        when(sources.search(any(SourceSearchRequest.class)))
                .thenThrow(new ApiException(HttpStatus.NOT_IMPLEMENTED, "SOURCE_SEARCH_UNAVAILABLE", "法源检索尚未接通"));
        mvc.perform(post("/v1/sources/search").header("Authorization", "Bearer token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"民法典\"}"))
                .andExpect(status().isNotImplemented())
                .andExpect(jsonPath("$.code").value("SOURCE_SEARCH_UNAVAILABLE"))
                .andExpect(jsonPath("$.retryable").value(false));
    }

    private static final class DocumentViewContent {
        static final String DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    }
}
