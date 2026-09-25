package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.CaseService;
import com.lexcyber.server.domain.TaskPolicies;
import com.lexcyber.server.domain.TaskService;
import com.lexcyber.server.domain.TaskView;
import com.lexcyber.server.engine.EngineTraceClient;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@RestController
@RequestMapping("/v1/tasks")
public class TaskTraceController {
    private final TaskService tasks;
    private final AuthService auth;
    private final CaseService cases;
    private final EngineTraceClient engine;

    public TaskTraceController(TaskService tasks, AuthService auth, CaseService cases, EngineTraceClient engine) {
        this.tasks = tasks;
        this.auth = auth;
        this.cases = cases;
        this.engine = engine;
    }

    @GetMapping("/{taskId}/trace")
    public ResponseEntity<Map<String, Object>> trace(
            @PathVariable UUID taskId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        TaskView task = tasks.find(taskId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "task not found"));
        authorize(task, authorization);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("taskId", task.id());
        body.put("executionId", task.executionId());
        body.put("events", engine.trace(task.executionId()));
        return ResponseEntity.ok(body);
    }

    private void authorize(TaskView task, String authorization) {
        if (task.caseId() != null && !task.caseId().isBlank()) {
            AuthAccount account = auth.require(authorization);
            cases.requireOwned(account.id(), task.caseId());
            return;
        }
        if (TaskPolicies.requiresAuth(tasks.metadataTaskType(task.id()))) {
            auth.require(authorization);
        }
    }
}
