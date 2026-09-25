package com.lexcyber.server.imports;

import com.lexcyber.server.api.ApiException;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import org.springframework.http.HttpStatus;

/**
 * Validates a bounded import ZIP once, then streams individual entries on demand.
 *
 * <p>The reader intentionally does not materialize all uncompressed entries. At
 * most the original transport bytes and one requested entry are held at once.</p>
 */
public final class ImportArchiveReader {
    private static final int MAX_ENTRIES = 10_000;
    private static final long MAX_TOTAL_BYTES = 64L * 1024 * 1024;
    private static final int MAX_ENTRY_BYTES = 50 * 1024 * 1024;
    private static final Pattern DRIVE_PATH = Pattern.compile("^[A-Za-z]:.*");
    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");

    private final byte[] rawZip;

    public ImportArchiveReader(byte[] rawZip) {
        if (rawZip == null || rawZip.length == 0) {
            throw invalid("ZIP archive is required");
        }
        this.rawZip = rawZip;
        validateArchive(rawZip);
    }

    public void clear() {
        Arrays.fill(rawZip, (byte) 0);
    }

    /** Returns the entry bytes after exact descriptor size and SHA-256 checks. Callers own the returned buffer. */
    public byte[] require(String path, long expectedSize, String expectedSha256) {
        String normalized = validatePath(path);
        if (expectedSize < 0 || expectedSize > MAX_ENTRY_BYTES) {
            throw invalid("Invalid expected size for ZIP entry: " + normalized);
        }
        if (expectedSha256 == null || !SHA256.matcher(expectedSha256).matches()) {
            throw invalid("Invalid expected SHA-256 for ZIP entry: " + normalized);
        }
        byte[] content = readEntry(normalized, expectedSize);
        if (content.length != expectedSize) {
            throw invalid("ZIP entry size mismatch: " + normalized);
        }
        if (!MessageDigest.isEqual(hexSha256(content).getBytes(java.nio.charset.StandardCharsets.US_ASCII),
                expectedSha256.getBytes(java.nio.charset.StandardCharsets.US_ASCII))) {
            throw invalid("ZIP entry SHA-256 mismatch: " + normalized);
        }
        return content;
    }

    private static void validateArchive(byte[] rawZip) {
        Set<String> names = new HashSet<>();
        Set<String> casefolded = new HashSet<>();
        long totalBytes = 0;
        int entryCount = 0;
        try (ZipInputStream archive = new ZipInputStream(new ByteArrayInputStream(rawZip))) {
            ZipEntry entry;
            while ((entry = archive.getNextEntry()) != null) {
                String rawName = entry.getName();
                if (entry.isDirectory()) {
                    validateDirectoryPath(rawName);
                    archive.closeEntry();
                    continue;
                }
                String name = validatePath(rawName);
                entryCount++;
                if (entryCount > MAX_ENTRIES) throw invalid("ZIP archive exceeds the entry limit");
                String folded = name.toLowerCase(Locale.ROOT);
                if (!names.add(name) || !casefolded.add(folded)) {
                    throw invalid("Duplicate or case-conflicting ZIP entry: " + name);
                }
                if (entry.getSize() > MAX_ENTRY_BYTES) {
                    throw invalid("ZIP entry exceeds the size limit: " + name);
                }
                totalBytes = discardBounded(archive, totalBytes, name);
                archive.closeEntry();
            }
        } catch (ApiException exception) {
            throw exception;
        } catch (IOException exception) {
            throw invalid("ZIP archive cannot be read", exception);
        }
    }

    private byte[] readEntry(String expectedPath, long expectedSize) {
        try (ZipInputStream archive = new ZipInputStream(new ByteArrayInputStream(rawZip))) {
            ZipEntry entry;
            while ((entry = archive.getNextEntry()) != null) {
                if (entry.isDirectory()) {
                    archive.closeEntry();
                    continue;
                }
                String name = validatePath(entry.getName());
                if (!expectedPath.equals(name)) {
                    discardBounded(archive, 0, name);
                    archive.closeEntry();
                    continue;
                }
                byte[] content = readEntry(archive, name, expectedSize);
                archive.closeEntry();
                return content;
            }
        } catch (ApiException exception) {
            throw exception;
        } catch (IOException exception) {
            throw invalid("ZIP archive cannot be read", exception);
        }
        throw invalid("Required ZIP entry is missing: " + expectedPath);
    }

    private static long discardBounded(ZipInputStream archive, long total, String name) throws IOException {
        byte[] buffer = new byte[8192];
        int entryBytes = 0;
        int read;
        while ((read = archive.read(buffer)) != -1) {
            entryBytes += read;
            total += read;
            if (entryBytes > MAX_ENTRY_BYTES) throw invalid("ZIP entry exceeds the size limit: " + name);
            if (total > MAX_TOTAL_BYTES) throw invalid("ZIP archive exceeds the uncompressed size limit");
        }
        return total;
    }

    private static byte[] readEntry(ZipInputStream archive, String name, long expectedSize) throws IOException {
        if (expectedSize > Integer.MAX_VALUE) throw invalid("ZIP entry exceeds the size limit: " + name);
        byte[] content = new byte[(int) expectedSize];
        int offset = 0;
        while (offset < content.length) {
            int read = archive.read(content, offset, content.length - offset);
            if (read == -1) break;
            offset += read;
        }
        if (archive.read() != -1 || offset != content.length) {
            throw invalid("ZIP entry size mismatch: " + name);
        }
        return content;
    }

    private static void validateDirectoryPath(String path) {
        if (path == null || path.isEmpty() || !path.endsWith("/")) throw invalid("Unsafe ZIP directory path");
        validatePath(path.substring(0, path.length() - 1));
    }

    private static String validatePath(String path) {
        if (path == null || path.isEmpty() || path.indexOf('\0') >= 0 || path.indexOf('\\') >= 0
                || path.startsWith("/") || DRIVE_PATH.matcher(path).matches() || path.endsWith("/")) {
            throw invalid("Unsafe ZIP entry path: " + String.valueOf(path));
        }
        for (String segment : path.split("/", -1)) {
            if (segment.isEmpty() || segment.equals(".") || segment.equals("..")) {
                throw invalid("Unsafe ZIP entry path: " + path);
            }
        }
        return path;
    }

    private static String hexSha256(byte[] content) {
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private static ApiException invalid(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "IMPORT_ARCHIVE_INVALID", message);
    }

    private static ApiException invalid(String message, Throwable cause) {
        return new ApiException(HttpStatus.BAD_REQUEST, "IMPORT_ARCHIVE_INVALID", message, cause);
    }
}
