package com.lexcyber.server.api;

import com.lexcyber.server.domain.TaskCreate;
import com.lexcyber.server.domain.TaskService;
import com.lexcyber.server.domain.TaskView;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/tasks")
public class TaskController {
    private final TaskService taskService;

    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @PostMapping
    public ResponseEntity<TaskView> create(@Valid @RequestBody TaskCreate request) {
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(taskService.create(request));
    }

    @GetMapping("/{taskId}")
    public ResponseEntity<TaskView> get(@PathVariable UUID taskId) {
        return taskService.find(taskId).map(ResponseEntity::ok).orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/{taskId}/retry")
    public ResponseEntity<TaskView> retry(@PathVariable UUID taskId) {
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(taskService.retry(taskId));
    }
}
