package com.lexcyber.server.storage;

import java.util.concurrent.ConcurrentHashMap;

public class InMemoryObjectStorage implements ObjectStorage {
    private final ConcurrentHashMap<String, byte[]> objects = new ConcurrentHashMap<>();

    @Override
    public void put(String key, byte[] data, String contentType) {
        objects.put(key, data.clone());
    }

    @Override
    public byte[] get(String key) {
        byte[] data = objects.get(key);
        if (data == null) throw new IllegalStateException("missing object: " + key);
        return data.clone();
    }

    public boolean contains(String key) {
        return objects.containsKey(key);
    }
}
