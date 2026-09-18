package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.domain.PageResponse;
import com.lexcyber.server.imports.ImportBatchCreate;
import com.lexcyber.server.imports.ImportBatchResponse;
import com.lexcyber.server.imports.ImportBatchView;
import com.lexcyber.server.imports.ImportItemResponse;
import com.lexcyber.server.imports.ImportService;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/v1/imports")
public class ImportController {
    private final AuthService auth;
    private final ImportService imports;

    public ImportController(AuthService auth, ImportService imports) {
        this.auth = auth;
        this.imports = imports;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ImportBatchResponse> create(
            @RequestParam("file") MultipartFile file,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        byte[] data;
        try {
            data = file.getBytes();
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "unable to read import package", ex);
        }
        ImportBatchView created = imports.createUploadedBatch(account.id(), new ImportBatchCreate(
                file.getOriginalFilename(), file.getContentType(), data, Map.of()));
        return ResponseEntity.status(HttpStatus.CREATED).body(ImportBatchResponse.from(created));
    }

    @GetMapping
    public PageResponse<ImportBatchResponse> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        List<ImportBatchResponse> items = imports.list(account.id(), page, size).stream()
                .map(ImportBatchResponse::from).toList();
        return new PageResponse<>(items, page, size, imports.count(account.id()));
    }

    @GetMapping("/{batchId}")
    public ImportBatchResponse get(
            @PathVariable UUID batchId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ImportBatchResponse.from(imports.get(account.id(), batchId));
    }

    @GetMapping("/{batchId}/items")
    public PageResponse<ImportItemResponse> items(
            @PathVariable UUID batchId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        List<ImportItemResponse> items = imports.listItems(account.id(), batchId, page, size).stream()
                .map(item -> ImportItemResponse.from(item, imports.listSteps(account.id(), batchId, item.id())))
                .toList();
        return new PageResponse<>(items, page, size, imports.countItems(account.id(), batchId));
    }

    @PostMapping("/{batchId}/validate")
    public ImportBatchResponse validate(
            @PathVariable UUID batchId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ImportBatchResponse.from(imports.validateBatch(account.id(), batchId));
    }

    @PostMapping("/{batchId}/approve")
    public ImportBatchResponse approve(
            @PathVariable UUID batchId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ImportBatchResponse.from(imports.approve(account.id(), batchId, account.id()));
    }

    @PostMapping("/{batchId}/apply")
    public ImportBatchResponse apply(
            @PathVariable UUID batchId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ImportBatchResponse.from(imports.apply(account.id(), batchId));
    }

    @PostMapping("/{batchId}/retry")
    public ImportBatchResponse retry(
            @PathVariable UUID batchId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        AuthAccount account = auth.require(authorization);
        return ImportBatchResponse.from(imports.retry(account.id(), batchId));
    }
}
