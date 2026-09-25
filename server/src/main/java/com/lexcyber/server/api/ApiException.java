package com.lexcyber.server.api;

import org.springframework.http.HttpStatus;

/** Public API error with a stable code separate from the human-readable message. */
public class ApiException extends RuntimeException {
    private final HttpStatus status;
    private final String code;
    private final java.util.Map<String, Object> details;

    public ApiException(HttpStatus status, String code, String message) {
        this(status, code, message, null, null);
    }

    public ApiException(HttpStatus status, String code, String message, java.util.Map<String, Object> details) {
        this(status, code, message, details, null);
    }

    public ApiException(HttpStatus status, String code, String message, Throwable cause) {
        this(status, code, message, null, cause);
    }

    private ApiException(HttpStatus status, String code, String message,
                         java.util.Map<String, Object> details, Throwable cause) {
        super(message, cause);
        this.status = status;
        this.code = code;
        this.details = details;
    }

    public HttpStatus status() {
        return status;
    }

    public String code() {
        return code;
    }

    public java.util.Map<String, Object> details() {
        return details;
    }
}
