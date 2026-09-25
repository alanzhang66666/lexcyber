package com.lexcyber.server.storage;

import com.lexcyber.server.api.ApiException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import org.springframework.http.HttpStatus;

/**
 * Single-container object storage. Keys are resolved below one persistent
 * directory and are never allowed to escape that directory.
 */
public class FileObjectStorage implements ObjectStorage {
    private final Path root;

    public FileObjectStorage(String rootDirectory) {
        this.root = Path.of(rootDirectory).toAbsolutePath().normalize();
        try {
            Files.createDirectories(this.root);
        } catch (IOException ex) {
            throw new IllegalStateException("unable to initialize object storage", ex);
        }
    }

    @Override
    public void put(String key, byte[] data, String contentType) {
        Path target = resolve(key);
        Path temporary = target.resolveSibling(target.getFileName() + "." + UUID.randomUUID() + ".tmp");
        try {
            Files.createDirectories(target.getParent());
            Files.write(temporary, data);
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception ex) {
            deleteQuietly(temporary);
            throw failure("文件存储失败", ex);
        }
    }

    @Override
    public byte[] get(String key) {
        try {
            return Files.readAllBytes(resolve(key));
        } catch (Exception ex) {
            throw failure("文件读取失败", ex);
        }
    }

    @Override
    public void delete(String key) {
        try {
            Files.deleteIfExists(resolve(key));
        } catch (Exception ex) {
            throw failure("文件删除失败", ex);
        }
    }

    private Path resolve(String key) {
        if (key == null || key.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_STORAGE_KEY", "文件存储键不能为空");
        }
        Path resolved = root.resolve(key).normalize();
        if (!resolved.startsWith(root)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_STORAGE_KEY", "文件存储键非法");
        }
        return resolved;
    }

    private ApiException failure(String message, Exception cause) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DOCUMENT_STORAGE_FAILED", message, cause);
    }

    private void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // The original storage failure is the actionable error.
        }
    }
}
