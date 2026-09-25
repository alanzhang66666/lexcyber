package com.lexcyber.server.api;

import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.settings.ModelAccessConfigUpdate;
import com.lexcyber.server.settings.ModelAccessConfigView;
import com.lexcyber.server.settings.ModelAccessService;
import jakarta.validation.Valid;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/settings/model-access")
public class ModelAccessController {
    private final AuthService auth;
    private final ModelAccessService models;
    private final ApiExceptionHandler errors = new ApiExceptionHandler();

    public ModelAccessController(AuthService auth, ModelAccessService models) {
        this.auth = auth;
        this.models = models;
    }

    @GetMapping
    public ModelAccessConfigView get(
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        auth.require(authorization);
        return models.get();
    }

    @PutMapping
    public ModelAccessConfigView put(
            @Valid @RequestBody ModelAccessConfigUpdate update,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return models.update(account.id(), update);
    }

    /** Keep model-config validation errors stable and free of submitted values. */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalidModelConfig(MethodArgumentNotValidException error) {
        String fields = error.getBindingResult().getFieldErrors().stream()
                .map(field -> field.getField())
                .collect(Collectors.joining(", "));
        return invalidModelConfig(fields.isBlank() ? "request" : fields);
    }

    /** Jackson errors can include an unknown property or a value in their message; expose neither. */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> unreadableModelConfig(HttpMessageNotReadableException error) {
        return invalidModelConfig(fieldNames(error));
    }

    private ResponseEntity<Map<String, Object>> invalidModelConfig(String fields) {
        return errors.api(new ApiException(
                HttpStatus.BAD_REQUEST,
                "INVALID_MODEL_CONFIG",
                "invalid model config fields: " + fields));
    }

    private static String fieldNames(Throwable error) {
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (current instanceof UnrecognizedPropertyException unknown) {
                return unknown.getPropertyName();
            }
            if (current instanceof JsonMappingException mapping) {
                Set<String> names = mapping.getPath().stream()
                        .map(JsonMappingException.Reference::getFieldName)
                        .filter(name -> name != null && !name.isBlank())
                        .collect(Collectors.toCollection(LinkedHashSet::new));
                if (!names.isEmpty()) {
                    return String.join(", ", names);
                }
            }
        }
        return "request";
    }
}
