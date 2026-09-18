package com.lexcyber.server.imports;

import com.lexcyber.server.storage.ObjectStorage;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class RawPackageStorage {
    private final ObjectStorage storage;

    public RawPackageStorage(ObjectStorage storage) {
        this.storage = storage;
    }

    public StoredRawPackage describe(UUID ownerAccountId, UUID batchId, String filename,
                                     String contentType, byte[] data) {
        byte[] snapshot = ImportPolicies.requireRawPackage(data);
        String normalizedName = ImportPolicies.normalizeFilename(filename);
        String normalizedType = ImportPolicies.normalizeContentType(contentType);
        String sha256 = ImportPolicies.sha256(snapshot);
        String key = ImportPolicies.storageKey(ownerAccountId, batchId, sha256);
        return new StoredRawPackage(key, normalizedName, normalizedType, snapshot.length, sha256);
    }

    public void put(StoredRawPackage raw, byte[] data) {
        byte[] snapshot = ImportPolicies.requireRawPackage(data);
        if (snapshot.length != raw.sizeBytes() || !ImportPolicies.sha256(snapshot).equals(raw.sha256())) {
            throw new IllegalArgumentException("raw package does not match its descriptor");
        }
        storage.put(raw.storageKey(), snapshot, raw.contentType());
    }

    public byte[] get(String storageKey) {
        return storage.get(storageKey);
    }

    public void delete(String storageKey) {
        storage.delete(storageKey);
    }

    public record StoredRawPackage(
            String storageKey,
            String filename,
            String contentType,
            long sizeBytes,
            String sha256) {
    }
}
