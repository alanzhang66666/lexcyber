package com.lexcyber.server.domain;

import java.security.MessageDigest;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

/** Pure upload rules shared by the document service and unit tests. */
public final class DocumentPolicies {
    public static final String ROLE_INPUT = "input";
    public static final String ROLE_ANNOTATION = "annotation";
    public static final String PDF = "application/pdf";
    public static final String DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private static final Set<String> ROLES = Set.of(ROLE_INPUT, ROLE_ANNOTATION);

    private DocumentPolicies() {
    }

    public static String requireRole(String role) {
        if (role == null || !ROLES.contains(role)) {
            throw new IllegalArgumentException("role must be input or annotation");
        }
        return role;
    }

    public static boolean isSupported(String filename, String contentType) {
        String name = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
        String type = contentType == null ? "" : contentType.toLowerCase(Locale.ROOT);
        if (name.endsWith(".pdf") || PDF.equals(type)) return true;
        return name.endsWith(".docx") || type.contains("wordprocessingml.document");
    }

    public static String detectFormat(String filename, String contentType) {
        String name = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
        String type = contentType == null ? "" : contentType.toLowerCase(Locale.ROOT);
        if (name.endsWith(".pdf") || PDF.equals(type)) return "pdf";
        return "docx";
    }

    public static String sha256Hex(byte[] data) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
            StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte item : digest) result.append(String.format("%02x", item & 0xff));
            return result.toString();
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 is required", ex);
        }
    }

    public static String requestHash(byte[] data) {
        return sha256Hex(data);
    }

    public static String storageKey(String caseId, String documentId, String sha256) {
        return "cases/" + caseId + "/" + documentId + "/" + sha256;
    }

    public static String newCaseId() {
        return "case-" + shortId();
    }

    public static String newDocumentId() {
        return "doc-" + shortId();
    }

    public static String normalizeFilename(String filename) {
        if (filename == null || filename.isBlank()) return "document";
        String value = filename.replace('\\', '/');
        int slash = value.lastIndexOf('/');
        return slash >= 0 ? value.substring(slash + 1) : value;
    }

    private static String shortId() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 16);
    }
}
