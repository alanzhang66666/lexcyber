package com.lexcyber.server.storage;

public interface ObjectStorage {
    void put(String key, byte[] data, String contentType);

    byte[] get(String key);

    void delete(String key);
}
