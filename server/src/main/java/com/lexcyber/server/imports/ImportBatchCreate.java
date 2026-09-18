package com.lexcyber.server.imports;

import java.util.Map;

public record ImportBatchCreate(
        String originalFilename,
        String contentType,
        byte[] data,
        Map<String, Object> metadata) {

    public ImportBatchCreate {
        data = data == null ? null : data.clone();
        metadata = ImportJson.copyMap(metadata);
    }

    @Override
    public byte[] data() {
        return data == null ? null : data.clone();
    }
}
