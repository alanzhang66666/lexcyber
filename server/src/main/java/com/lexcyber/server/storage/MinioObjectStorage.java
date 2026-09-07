package com.lexcyber.server.storage;

import com.lexcyber.server.api.ApiException;
import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import org.springframework.http.HttpStatus;

/** Stores document bytes in MinIO. Persistence failure is reported as DOCUMENT_STORAGE_FAILED. */
public class MinioObjectStorage implements ObjectStorage {
    private final MinioClient client;
    private final String bucket;
    private volatile boolean bucketReady;

    public MinioObjectStorage(String endpoint, String accessKey, String secretKey, String bucket) {
        this.client = MinioClient.builder().endpoint(endpoint).credentials(accessKey, secretKey).build();
        this.bucket = bucket;
    }

    @Override
    public void put(String key, byte[] data, String contentType) {
        try {
            ensureBucket();
            String type = contentType == null || contentType.isBlank() ? "application/octet-stream" : contentType;
            client.putObject(PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(key)
                    .stream(new ByteArrayInputStream(data), data.length, -1)
                    .contentType(type)
                    .build());
        } catch (ApiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DOCUMENT_STORAGE_FAILED", "文件存储失败", ex);
        }
    }

    @Override
    public byte[] get(String key) {
        try {
            ensureBucket();
            try (InputStream stream = client.getObject(GetObjectArgs.builder().bucket(bucket).object(key).build())) {
                return stream.readAllBytes();
            }
        } catch (ApiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DOCUMENT_STORAGE_FAILED", "文件读取失败", ex);
        }
    }

    private void ensureBucket() {
        if (bucketReady) return;
        synchronized (this) {
            if (bucketReady) return;
            try {
                boolean exists = client.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
                if (!exists) {
                    client.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
                }
                bucketReady = true;
            } catch (Exception ex) {
                throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DOCUMENT_STORAGE_FAILED", "文件存储失败", ex);
            }
        }
    }
}
