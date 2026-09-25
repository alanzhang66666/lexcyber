package com.lexcyber.server.config;

import com.lexcyber.server.storage.MinioObjectStorage;
import com.lexcyber.server.storage.ObjectStorage;
import com.lexcyber.server.storage.FileObjectStorage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StorageConfig {
    @Bean
    public ObjectStorage objectStorage(
            @Value("${storage.provider:filesystem}") String provider,
            @Value("${storage.root:/data/objects}") String root,
            @Value("${minio.endpoint}") String endpoint,
            @Value("${minio.access-key}") String accessKey,
            @Value("${minio.secret-key}") String secretKey,
            @Value("${minio.bucket}") String bucket) {
        if ("filesystem".equalsIgnoreCase(provider)) {
            return new FileObjectStorage(root);
        }
        return new MinioObjectStorage(endpoint, accessKey, secretKey, bucket);
    }
}
