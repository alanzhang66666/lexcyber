package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.TaskCreate;
import com.lexcyber.server.domain.TaskPolicies;
import com.lexcyber.server.domain.TaskService;
import com.lexcyber.server.domain.TaskView;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import jakarta.validation.Valid;
import java.util.Map;
import java.util.UUID;
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
    private final TaskService taskService;
    private final AuthService auth;
    private final CaseService cases;
    private final boolean sentencingEnabled;

    public TaskController(TaskService taskService, AuthService auth, CaseService cases) {
        this(taskService, auth, cases, false);
    }

    @Autowired
    public TaskController(TaskService taskService, AuthService auth, CaseService cases,
                          @Value("${sentencing.enabled:false}") boolean sentencingEnabled) {
        this.taskService = taskService;
        this.auth = auth;
        this.cases = cases;
        this.sentencingEnabled = sentencingEnabled;
    }

    @PostMapping
    public ResponseEntity<TaskView> create(@Valid @RequestBody TaskCreate request,
                                           @RequestHeader(value = "Authorization", required = false) String authorization) {
        authorizeCase(request.caseId(), authorization);
        TaskPolicies.requireSupported(request.metadata(), sentencingEnabled);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(taskService.create(request));
    }

    @GetMapping("/{taskId}")
    public ResponseEntity<TaskView> get(@PathVariable UUID taskId,
                                        @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView view = taskService.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorizeCase(view.caseId(), authorization);
        return ResponseEntity.ok(view);
    }

    @GetMapping("/{taskId}/result")
    public ResponseEntity<Map<String, Object>> result(@PathVariable UUID taskId,
                                                      @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView view = taskService.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorizeCase(view.caseId(), authorization);
        return ResponseEntity.ok(taskService.result(taskId));
    }

    @PostMapping("/{taskId}/retry")
    public ResponseEntity<TaskView> retry(@PathVariable UUID taskId,
                                          @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView view = taskService.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorizeCase(view.caseId(), authorization);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(taskService.retry(taskId));
    }

    private void authorizeCase(String caseId, String authorization) {
        if (caseId == null || caseId.isBlank()) return;
        AuthAccount account = auth.require(authorization);
        cases.requireOwned(account.id(), caseId);
    }
}
