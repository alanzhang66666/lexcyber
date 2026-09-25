package com.lexcyber.server.imports;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.Test;

class ImportArchiveReaderTest {
    @Test
    void requireReadsTheRequestedEntryWithoutRecursing() throws Exception {
        byte[] expected = "import archive payload".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ZipOutputStream archive = new ZipOutputStream(buffer)) {
            archive.putNextEntry(new ZipEntry("items/item-1/material.txt"));
            archive.write(expected);
            archive.closeEntry();
        }

        ImportArchiveReader reader = new ImportArchiveReader(buffer.toByteArray());
        String sha256 = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(expected));

        assertArrayEquals(expected, reader.require("items/item-1/material.txt", expected.length, sha256));
    }
}
