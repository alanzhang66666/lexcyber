package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.DocumentService;
import com.lexcyber.server.domain.TaskCreate;
import com.lexcyber.server.domain.TaskService;
import com.lexcyber.server.domain.TaskView;
import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/v1/tasks")
public class TaskController {
    private static final String DOCUMENT_PARSE = "document.parse";

    private final TaskService taskService;
    private final AuthService auth;
    private final CaseService cases;
    private final DocumentService documents;

    public TaskController(TaskService taskService, AuthService auth, CaseService cases) {
        this(taskService, auth, cases, null);
    }

    @Autowired
    public TaskController(TaskService taskService, AuthService auth, CaseService cases, DocumentService documents) {
        this.taskService = taskService;
        this.auth = auth;
        this.cases = cases;
        this.documents = documents;
    }

    @PostMapping
    public ResponseEntity<TaskView> create(@Valid @RequestBody TaskCreate request,
                                           @RequestHeader(value = "Authorization", required = false) String authorization) {
        boolean parse = isDocumentParse(request.metadata());
        AuthAccount account = null;
        if (parse || hasCase(request.caseId())) {
            account = auth.require(authorization);
        }
        TaskCreate bound = bindDocumentParse(account, request, parse);
        if (hasCase(bound.caseId())) {
            cases.requireOwned(account.id(), bound.caseId());
        }
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(taskService.create(bound));
    }

    @GetMapping("/{taskId}")
    public ResponseEntity<TaskView> get(@PathVariable UUID taskId,
                                        @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView view = taskService.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorizeTask(view, authorization);
        return ResponseEntity.ok(view);
    }

    @GetMapping("/{taskId}/result")
    public ResponseEntity<Map<String, Object>> result(@PathVariable UUID taskId,
                                                      @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView view = taskService.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorizeTask(view, authorization);
        return ResponseEntity.ok(taskService.result(taskId));
    }

    @PostMapping("/{taskId}/retry")
    public ResponseEntity<TaskView> retry(@PathVariable UUID taskId,
                                          @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView view = taskService.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorizeTask(view, authorization);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(taskService.retry(taskId));
    }

    private TaskCreate bindDocumentParse(AuthAccount account, TaskCreate request, boolean parse) {
        if (!parse) {
            return request;
        }
        if (account == null || documents == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "session required");
        }
        Object rawId = request.metadata() == null ? null : request.metadata().get("documentId");
        if (rawId == null && request.metadata() != null) {
            rawId = request.metadata().get("document_id");
        }
        if (rawId == null || String.valueOf(rawId).isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "document.parse requires documentId");
        }
        DocumentService.StoredDocument document = documents.requireOwnedForParse(account.id(), String.valueOf(rawId).trim());
        Map<String, Object> metadata = new LinkedHashMap<>(request.metadata() == null ? Map.of() : request.metadata());
        metadata.put("taskType", DOCUMENT_PARSE);
        metadata.put("documentId", document.id());
        metadata.put("storageKey", document.storageKey());
        metadata.put("filename", document.filename());
        metadata.put("contentType", document.contentType());
        metadata.put("schemaVersion", "document.parse.v1");
        return new TaskCreate(request.query(), document.caseId(), request.sessionId(), metadata);
    }

    private void authorizeTask(TaskView view, String authorization) {
        if (hasCase(view.caseId())) {
            AuthAccount account = auth.require(authorization);
            cases.requireOwned(account.id(), view.caseId());
            return;
        }
        if (DOCUMENT_PARSE.equals(taskService.metadataTaskType(view.id()))) {
            auth.require(authorization);
        }
    }

    private static boolean isDocumentParse(Map<String, Object> metadata) {
        if (metadata == null) return false;
        Object value = metadata.get("taskType");
        if (value == null) return false;
        return DOCUMENT_PARSE.equals(String.valueOf(value).trim());
    }

    private static boolean hasCase(String caseId) {
        return caseId != null && !caseId.isBlank();
    }
}
