package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.storage.InMemoryObjectStorage;
import com.lexcyber.server.storage.ObjectStorage;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
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

    @Test
    void uploadDeletesStoredObjectWhenLaterWorkFails() {
        CaseService cases = mock(CaseService.class);
        when(cases.requireOwned(any(), any())).thenReturn(new CaseView("case-1", "t", "CN", null, Map.of(),
                OffsetDateTime.now(), OffsetDateTime.now()));
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject(anyString(), eq(Long.class), any())).thenReturn(0L);
        TaskService tasks = mock(TaskService.class);
        when(tasks.create(any())).thenThrow(new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_UNAVAILABLE", "down"));
        InMemoryObjectStorage storage = spy(new InMemoryObjectStorage());
        DocumentService service = new DocumentService(jdbc, cases, tasks, storage);

        ApiException error = assertThrows(ApiException.class, () -> service.upload(
                UUID.randomUUID(), "case-1", "notes.pdf", "application/pdf", "hello".getBytes(), "input", null));
        assertEquals("ENGINE_UNAVAILABLE", error.code());
        ArgumentCaptor<String> key = ArgumentCaptor.forClass(String.class);
        verify(storage).put(key.capture(), any(), any());
        verify(storage).delete(key.getValue());
        assertFalse(storage.contains(key.getValue()));
    }

    @Test
    void uploadKeepsOriginalErrorWhenRollbackDeleteFails() {
        CaseService cases = mock(CaseService.class);
        when(cases.requireOwned(any(), any())).thenReturn(new CaseView("case-1", "t", "CN", null, Map.of(),
                OffsetDateTime.now(), OffsetDateTime.now()));
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.queryForObject(anyString(), eq(Long.class), any())).thenReturn(0L);
        TaskService tasks = mock(TaskService.class);
        when(tasks.create(any())).thenThrow(new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_UNAVAILABLE", "down"));
        ObjectStorage storage = mock(ObjectStorage.class);
        doThrow(new RuntimeException("delete failed")).when(storage).delete(any());
        DocumentService service = new DocumentService(jdbc, cases, tasks, storage);

        ApiException error = assertThrows(ApiException.class, () -> service.upload(
                UUID.randomUUID(), "case-1", "notes.pdf", "application/pdf", "hello".getBytes(), "input", null));
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, error.status());
        assertEquals("ENGINE_UNAVAILABLE", error.code());
        verify(storage).delete(any());
    }
}
