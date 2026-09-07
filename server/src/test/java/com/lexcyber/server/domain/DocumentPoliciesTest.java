package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class DocumentPoliciesTest {
    @Test
    void acceptsInputAndAnnotationRolesOnly() {
        assertEquals("input", DocumentPolicies.requireRole("input"));
        assertEquals("annotation", DocumentPolicies.requireRole("annotation"));
        assertThrows(IllegalArgumentException.class, () -> DocumentPolicies.requireRole("kind"));
        assertThrows(IllegalArgumentException.class, () -> DocumentPolicies.requireRole(null));
    }

    @Test
    void acceptsPdfAndDocxOnly() {
        assertTrue(DocumentPolicies.isSupported("案情材料.pdf", "application/pdf"));
        assertTrue(DocumentPolicies.isSupported("notes.docx", DocumentPolicies.DOCX));
        assertFalse(DocumentPolicies.isSupported("notes.txt", "text/plain"));
        assertFalse(DocumentPolicies.isSupported("image.png", "image/png"));
    }

    @Test
    void hashesContentAndBuildsStorageKey() {
        byte[] body = "hello".getBytes();
        String digest = DocumentPolicies.sha256Hex(body);
        assertEquals(64, digest.length());
        assertEquals(digest, DocumentPolicies.requestHash(body));
        assertEquals("cases/case-1/doc-1/" + digest, DocumentPolicies.storageKey("case-1", "doc-1", digest));
    }

    @Test
    void generatesBusinessIds() {
        assertTrue(DocumentPolicies.newCaseId().startsWith("case-"));
        assertTrue(DocumentPolicies.newDocumentId().startsWith("doc-"));
        assertEquals("案情材料.docx", DocumentPolicies.normalizeFilename("C:\\\\tmp\\\\案情材料.docx"));
    }
}
