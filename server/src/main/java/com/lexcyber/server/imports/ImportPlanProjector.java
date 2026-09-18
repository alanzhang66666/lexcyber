package com.lexcyber.server.imports;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.CaseCreate;
import com.lexcyber.server.domain.CaseEventDocumentUpdate;
import com.lexcyber.server.domain.FactItem;
import com.lexcyber.server.domain.ModuleStateUpdate;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;

/** Strictly projects one Engine-normalized import item to existing public-domain requests. */
public final class ImportPlanProjector {
    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");

    private final Map<String, Object> item;

    public ImportPlanProjector(Map<String, Object> item) {
        if (item == null) {
            throw invalid("Normalized import item is required");
        }
        this.item = jsonObject(item, "$item");
    }

    public ImportPlan project(
            Map<String, String> documentIdMap,
            String module,
            int currentVersion) {
        return new ImportPlan(
                caseCreate(),
                facts(documentIdMap),
                moduleState(module, currentVersion),
                eventBindings(documentIdMap),
                files());
    }

    public CaseCreate caseCreate() {
        Map<String, Object> value = requiredObject(item, "case_create", "$item");
        String title = requiredNonBlankString(value, "title", "$item.case_create");
        String jurisdiction = requiredNonBlankString(value, "jurisdiction", "$item.case_create");
        String dateText = requiredNonBlankString(value, "asOfDate", "$item.case_create");
        LocalDate asOfDate;
        try {
            asOfDate = LocalDate.parse(dateText);
        } catch (DateTimeException exception) {
            throw invalid("$item.case_create.asOfDate must be an ISO local date", exception);
        }
        Map<String, Object> metadata = requiredObject(value, "metadata", "$item.case_create");
        return new CaseCreate(title, jurisdiction, asOfDate, metadata);
    }

    public List<FactItem> facts(Map<String, String> documentIdMap) {
        Map<String, String> ids = requireDocumentIdMap(documentIdMap);
        List<Object> values = requiredList(item, "facts", "$item");
        List<FactItem> projected = new ArrayList<>(values.size());
        for (int index = 0; index < values.size(); index++) {
            String path = "$item.facts[" + index + "]";
            Map<String, Object> value = objectValue(values.get(index), path);
            String externalDocumentId = requiredNonBlankString(value, "sourceDocumentId", path);
            projected.add(new FactItem(
                    requiredNonBlankString(value, "id", path),
                    requiredNonBlankString(value, "key", path),
                    requiredString(value, "value", path),
                    requiredNonBlankString(value, "locator", path),
                    mappedDocumentId(ids, externalDocumentId, path + ".sourceDocumentId"),
                    optionalString(value, "verificationStatus", path),
                    optionalString(value, "sourceVersion", path)));
        }
        return List.copyOf(projected);
    }

    public ModuleStateUpdate moduleState(String module, int currentVersion) {
        if (module == null || module.isBlank()) {
            throw invalid("Module name is required");
        }
        if (currentVersion < 0) {
            throw invalid("Current module version must not be negative");
        }
        Map<String, Object> modules = requiredObject(item, "modules", "$item");
        Map<String, Object> value = requiredObject(modules, module, "$item.modules");
        String path = "$item.modules." + module;
        requiredNonBlankString(value, "caseId", path);
        String normalizedModule = requiredNonBlankString(value, "module", path);
        if (!module.equals(normalizedModule)) {
            throw invalid(path + ".module does not match the requested module");
        }
        requiredNonNegativeInteger(value, "version", path);
        return new ModuleStateUpdate(
                requiredNonBlankString(value, "applicability", path),
                requiredObject(value, "content", path),
                optionalString(value, "sourceVersion", path),
                currentVersion);
    }

    public List<EventBinding> eventBindings(Map<String, String> documentIdMap) {
        Map<String, String> ids = requireDocumentIdMap(documentIdMap);
        List<Object> values = requiredList(item, "event_bindings", "$item");
        List<EventBinding> projected = new ArrayList<>();
        for (int index = 0; index < values.size(); index++) {
            String path = "$item.event_bindings[" + index + "]";
            Map<String, Object> value = objectValue(values.get(index), path);
            String eventId = requiredNonBlankString(value, "eventId", path);
            if (!value.containsKey("documentId")) {
                continue;
            }
            String externalDocumentId = requiredNonBlankString(value, "documentId", path);
            projected.add(new EventBinding(
                    eventId,
                    new CaseEventDocumentUpdate(
                            mappedDocumentId(ids, externalDocumentId, path + ".documentId"),
                            optionalNonBlankString(value, "locator", path))));
        }
        return List.copyOf(projected);
    }

    public List<FilePlan> files() {
        List<Object> values = requiredList(item, "files", "$item");
        List<FilePlan> projected = new ArrayList<>(values.size());
        for (int index = 0; index < values.size(); index++) {
            String path = "$item.files[" + index + "]";
            Map<String, Object> value = objectValue(values.get(index), path);
            String hash = requiredNonBlankString(value, "sha256", path);
            if (!SHA256.matcher(hash).matches()) {
                throw invalid(path + ".sha256 must be a lowercase SHA-256 value");
            }
            projected.add(new FilePlan(
                    requiredNonBlankString(value, "role", path),
                    requiredNonBlankString(value, "media_type", path),
                    requiredNonBlankString(value, "path", path),
                    hash,
                    optionalString(value, "source_version", path),
                    requiredNonBlankString(value, "document_id", path),
                    requiredNonBlankString(value, "file_id", path),
                    requiredNonNegativeInteger(value, "size", path)));
        }
        return List.copyOf(projected);
    }

    public record ImportPlan(
            CaseCreate caseCreate,
            List<FactItem> facts,
            ModuleStateUpdate moduleState,
            List<EventBinding> eventBindings,
            List<FilePlan> files) {
    }

    public record EventBinding(String eventId, CaseEventDocumentUpdate update) {
    }

    public record FilePlan(
            String role,
            String mediaType,
            String path,
            String sha256,
            String sourceVersion,
            String documentId,
            String fileId,
            long size) {
    }

    private static Map<String, String> requireDocumentIdMap(Map<String, String> documentIdMap) {
        if (documentIdMap == null) {
            throw invalid("Document ID map is required");
        }
        Map<String, String> copy = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : documentIdMap.entrySet()) {
            if (entry.getKey() == null || entry.getKey().isBlank()
                    || entry.getValue() == null || entry.getValue().isBlank()) {
                throw invalid("Document ID map must contain non-blank string keys and values");
            }
            copy.put(entry.getKey(), entry.getValue());
        }
        return Collections.unmodifiableMap(copy);
    }

    private static String mappedDocumentId(Map<String, String> ids, String externalId, String path) {
        String mapped = ids.get(externalId);
        if (mapped == null || mapped.isBlank()) {
            throw invalid(path + " has no uploaded document ID mapping");
        }
        return mapped;
    }

    private static Map<String, Object> requiredObject(Map<String, Object> parent, String key, String path) {
        if (!parent.containsKey(key)) {
            throw invalid(path + "." + key + " is required");
        }
        return objectValue(parent.get(key), path + "." + key);
    }

    private static Map<String, Object> objectValue(Object value, String path) {
        if (!(value instanceof Map<?, ?> map)) {
            throw invalid(path + " must be an object");
        }
        return jsonObject(map, path);
    }

    private static Map<String, Object> jsonObject(Map<?, ?> value, String path) {
        Map<String, Object> copy = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw invalid(path + " must contain only string keys");
            }
            copy.put(key, jsonValue(entry.getValue(), path + "." + key));
        }
        return Collections.unmodifiableMap(copy);
    }

    private static Object jsonValue(Object value, String path) {
        if (value == null || value instanceof String || value instanceof Boolean || value instanceof Number) {
            return value;
        }
        if (value instanceof Map<?, ?> map) {
            return jsonObject(map, path);
        }
        if (value instanceof List<?> list) {
            List<Object> copy = new ArrayList<>(list.size());
            for (int index = 0; index < list.size(); index++) {
                copy.add(jsonValue(list.get(index), path + "[" + index + "]"));
            }
            return Collections.unmodifiableList(copy);
        }
        throw invalid(path + " contains an unsupported value type");
    }

    private static List<Object> requiredList(Map<String, Object> parent, String key, String path) {
        if (!parent.containsKey(key)) {
            throw invalid(path + "." + key + " is required");
        }
        Object value = parent.get(key);
        if (!(value instanceof List<?> list)) {
            throw invalid(path + "." + key + " must be an array");
        }
        return new ArrayList<>(list);
    }

    private static String requiredString(Map<String, Object> parent, String key, String path) {
        if (!parent.containsKey(key) || !(parent.get(key) instanceof String value)) {
            throw invalid(path + "." + key + " must be a string");
        }
        return value;
    }

    private static String requiredNonBlankString(Map<String, Object> parent, String key, String path) {
        String value = requiredString(parent, key, path);
        if (value.isBlank()) {
            throw invalid(path + "." + key + " must not be blank");
        }
        return value;
    }

    private static String optionalString(Map<String, Object> parent, String key, String path) {
        if (!parent.containsKey(key) || parent.get(key) == null) {
            return null;
        }
        if (!(parent.get(key) instanceof String value)) {
            throw invalid(path + "." + key + " must be a string or null");
        }
        return value;
    }

    private static String optionalNonBlankString(Map<String, Object> parent, String key, String path) {
        String value = optionalString(parent, key, path);
        if (value != null && value.isBlank()) {
            throw invalid(path + "." + key + " must not be blank");
        }
        return value;
    }

    private static long requiredNonNegativeInteger(Map<String, Object> parent, String key, String path) {
        if (!parent.containsKey(key)) {
            throw invalid(path + "." + key + " is required");
        }
        Object value = parent.get(key);
        long result;
        try {
            if (value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long) {
                result = ((Number) value).longValue();
            } else if (value instanceof BigInteger integer) {
                result = integer.longValueExact();
            } else if (value instanceof BigDecimal decimal) {
                result = decimal.longValueExact();
            } else {
                throw invalid(path + "." + key + " must be an integer");
            }
        } catch (ArithmeticException exception) {
            throw invalid(path + "." + key + " must fit in a 64-bit integer", exception);
        }
        if (result < 0) {
            throw invalid(path + "." + key + " must not be negative");
        }
        return result;
    }

    private static ApiException invalid(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "IMPORT_PLAN_INVALID", message);
    }

    private static ApiException invalid(String message, Throwable cause) {
        return new ApiException(HttpStatus.BAD_REQUEST, "IMPORT_PLAN_INVALID", message, cause);
    }
}
