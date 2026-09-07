package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.storage.ObjectStorage;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;

class DocumentServiceValidationTest {
    @Test
    void unsupportedTypeIs415() {
        CaseService cases = mock(CaseService.class);
        when(cases.requireOwned(any(), any())).thenReturn(new CaseView("case-1", "t", "CN", null, Map.of(),
                OffsetDateTime.now(), OffsetDateTime.now()));
        DocumentService service = new DocumentService(mock(JdbcTemplate.class), cases, mock(TaskService.class), mock(ObjectStorage.class));
        ApiException error = assertThrows(ApiException.class, () -> service.upload(
                UUID.randomUUID(), "case-1", "notes.txt", "text/plain", "hello".getBytes(), "input", null));
        assertEquals(HttpStatus.UNSUPPORTED_MEDIA_TYPE, error.status());
        assertEquals("UNSUPPORTED_DOCUMENT_TYPE", error.code());
    }

    @Test
    void invalidRoleIs400() {
        CaseService cases = mock(CaseService.class);
        when(cases.requireOwned(any(), any())).thenReturn(new CaseView("case-1", "t", "CN", null, Map.of(),
                OffsetDateTime.now(), OffsetDateTime.now()));
        DocumentService service = new DocumentService(mock(JdbcTemplate.class), cases, mock(TaskService.class), mock(ObjectStorage.class));
        ApiException error = assertThrows(ApiException.class, () -> service.upload(
                UUID.randomUUID(), "case-1", "notes.pdf", "application/pdf", "hello".getBytes(), "kind", null));
        assertEquals(HttpStatus.BAD_REQUEST, error.status());
    }
}
