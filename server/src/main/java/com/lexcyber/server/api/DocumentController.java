package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.DocumentService;
import com.lexcyber.server.domain.DocumentView;
import com.lexcyber.server.domain.PageResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class DocumentController {
    private final AuthService auth;
    private final DocumentService documents;

    public DocumentController(AuthService auth, DocumentService documents) {
        this.auth = auth;
        this.documents = documents;
    }

    @PostMapping(path = "/v1/cases/{caseId}/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DocumentView> upload(@PathVariable String caseId,
                                               @RequestParam("file") MultipartFile file,
                                               @RequestParam("role") String role,
                                               @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
                                               @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        byte[] data;
        try {
            data = file.getBytes();
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "unable to read uploaded file", ex);
        }
        DocumentView view = documents.upload(account.id(), caseId, file.getOriginalFilename(), file.getContentType(),
                data, role, idempotencyKey);
        return ResponseEntity.status(HttpStatus.CREATED).body(view);
    }

    @GetMapping("/v1/cases/{caseId}/documents")
    public PageResponse<DocumentView> list(@PathVariable String caseId,
                                           @RequestParam(required = false) String role,
                                           @RequestParam(defaultValue = "0") int page,
                                           @RequestParam(defaultValue = "20") int size,
                                           @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return documents.list(account.id(), caseId, role, page, size);
    }

    @GetMapping("/v1/documents/{documentId}")
    public DocumentView get(@PathVariable String documentId,
                            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return documents.requireOwned(account.id(), documentId);
    }
}
