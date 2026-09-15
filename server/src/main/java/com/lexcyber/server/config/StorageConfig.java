package com.lexcyber.server.config;

import com.lexcyber.server.storage.MinioObjectStorage;
import com.lexcyber.server.storage.ObjectStorage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StorageConfig {
    @Bean
    public ObjectStorage objectStorage(
            @Value("${minio.endpoint}") String endpoint,
            @Value("${minio.access-key}") String accessKey,
            @Value("${minio.secret-key}") String secretKey,
            @Value("${minio.bucket}") String bucket) {
        return new MinioObjectStorage(endpoint, accessKey, secretKey, bucket);
    }
}
