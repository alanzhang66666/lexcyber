package com.lexcyber.server.api;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.server.ResponseStatusException;

/** Stable public error envelope shared by auth, task and review endpoints. */
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> api(ApiException error) {
        return body(error.status(), error.code(), error.getMessage());
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, Object>> status(ResponseStatusException error) {
        HttpStatus status = HttpStatus.resolve(error.getStatusCode().value());
        HttpStatus resolved = status == null ? HttpStatus.INTERNAL_SERVER_ERROR : status;
        return body(resolved, code(error.getReason(), resolved), error.getReason());
    }

    @ExceptionHandler({MissingServletRequestParameterException.class, MissingServletRequestPartException.class})
    public ResponseEntity<Map<String, Object>> missingPart(Exception error) {
        return body(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", error.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> validation(MethodArgumentNotValidException error) {
        String message = error.getBindingResult().getFieldErrors().stream()
                .findFirst().map(item -> item.getField() + ": " + item.getDefaultMessage())
                .orElse("request validation failed");
        return body(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", message);
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, Object>> state(IllegalStateException error) {
        return body(HttpStatus.CONFLICT, "INVALID_STATE", error.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> unexpected(Exception error) {
        return body(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "unexpected server error");
    }

    private ResponseEntity<Map<String, Object>> body(HttpStatus status, String code, String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("code", code);
        payload.put("message", message == null ? status.getReasonPhrase() : message);
        payload.put("traceId", UUID.randomUUID().toString());
        payload.put("retryable", status == HttpStatus.SERVICE_UNAVAILABLE
                || (status.is5xxServerError() && status != HttpStatus.NOT_IMPLEMENTED));
        return ResponseEntity.status(status).body(payload);
    }

    private String code(String reason, HttpStatus status) {
        if (status == HttpStatus.UNAUTHORIZED) return "UNAUTHORIZED";
        if (reason == null || reason.isBlank()) return status.name();
        if (reason.equals(reason.toUpperCase(Locale.ROOT)) && reason.matches("[A-Z0-9_]+")) return reason;
        return reason.toUpperCase(Locale.ROOT).replaceAll("[^A-Z0-9]+", "_");
    }
}
