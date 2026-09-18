package com.lexcyber.server.imports;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.DocumentPolicies;
import java.util.UUID;
import org.springframework.http.HttpStatus;

public final class ImportPolicies {
    public static final long MAX_RAW_PACKAGE_BYTES = 50L * 1024L * 1024L;
    public static final String ZIP_CONTENT_TYPE = "application/zip";

    private ImportPolicies() {
    }

    public static byte[] requireRawPackage(byte[] data) {
        if (data == null || data.length == 0) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "import package is required");
        }
        if (data.length > MAX_RAW_PACKAGE_BYTES) {
            throw new ApiException(HttpStatus.PAYLOAD_TOO_LARGE, "IMPORT_PACKAGE_TOO_LARGE", "导入包超过 50MB 限制");
        }
        return data;
    }

    public static String normalizeFilename(String filename) {
        String normalized = DocumentPolicies.normalizeFilename(filename).trim();
        if (normalized.isEmpty()) normalized = "case-import.zip";
        if (normalized.length() > 255) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "filename is too long");
        }
        return normalized;
    }

    public static String normalizeContentType(String contentType) {
        return contentType == null || contentType.isBlank() ? "application/octet-stream" : contentType.trim();
    }

    public static String sha256(byte[] data) {
        return DocumentPolicies.sha256Hex(data);
    }

    public static String storageKey(UUID ownerAccountId, UUID batchId, String sha256) {
        return "imports/" + ownerAccountId + "/" + batchId + "/" + sha256;
    }
}
