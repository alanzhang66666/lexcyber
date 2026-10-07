package com.lexcyber.server.engine;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.lexcyber.server.api.ApiException;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

class DraftExportEngineClientTest {
    private HttpServer server;
    private AtomicReference<String> path;
    private AtomicReference<String> token;
    private AtomicReference<String> requestBody;

    @BeforeEach
    void openServer() throws IOException {
        path = new AtomicReference<>();
        token = new AtomicReference<>();
        requestBody = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/draft-exports/docx", this::recordRequest);
        server.start();
    }

    @AfterEach
    void closeServer() {
        server.stop(0);
    }

    @Test
    void sendsServiceTokenExactUriAndAcceptsDocx() {
        byte[] expected = validDocx();
        DraftExportEngineClient client = client("secret");

        byte[] actual = client.render(Map.of("case_id", "case", "body", "正文"));

        assertArrayEquals(expected, actual);
        assertEquals("/internal/v1/draft-exports/docx", path.get());
        assertEquals("secret", token.get());
        org.junit.jupiter.api.Assertions.assertTrue(requestBody.get().contains("\"body\":\"正文\""));
    }

    @Test
    void rejectsWrongMimeEmptyAndNonZipResponses() {
        DraftExportEngineClient client = client("secret");
        for (ResponseCase response : new ResponseCase[] {
                new ResponseCase("application/json", validDocx()),
                new ResponseCase("application/vnd.openxmlformats-officedocument.wordprocessingml.document", new byte[0]),
                new ResponseCase("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "nope".getBytes(StandardCharsets.UTF_8))
        }) {
            server.removeContext("/internal/v1/draft-exports/docx");
            server.createContext("/internal/v1/draft-exports/docx", exchange -> respond(exchange, 200,
                    response.contentType(), response.body()));
            ApiException error = assertThrows(ApiException.class, () -> client.render(Map.of("body", "正文")));
            assertEquals("DRAFT_EXPORT_UNAVAILABLE", error.code());
        }
    }

    @Test
    void mapsEngineErrorsToStableCodes() {
        DraftExportEngineClient client = client("secret");
        server.removeContext("/internal/v1/draft-exports/docx");
        server.createContext("/internal/v1/draft-exports/docx", exchange -> respond(exchange, 422,
                "application/json", "blocked".getBytes(StandardCharsets.UTF_8)));
        assertEquals("DRAFT_EXPORT_BLOCKED",
                assertThrows(ApiException.class, () -> client.render(Map.of())).code());

        server.removeContext("/internal/v1/draft-exports/docx");
        server.createContext("/internal/v1/draft-exports/docx", exchange -> respond(exchange, 503,
                "application/json", "down".getBytes(StandardCharsets.UTF_8)));
        assertEquals("DRAFT_EXPORT_UNAVAILABLE",
                assertThrows(ApiException.class, () -> client.render(Map.of())).code());
    }

    @Test
    void unreachableEngineFailsClosed() {
        DraftExportEngineClient client = new DraftExportEngineClient(
                RestClient.builder(), "http://127.0.0.1:1", "secret");
        assertEquals("DRAFT_EXPORT_UNAVAILABLE",
                assertThrows(ApiException.class, () -> client.render(Map.of())).code());
    }

    private DraftExportEngineClient client(String serviceToken) {
        return new DraftExportEngineClient(RestClient.builder(),
                "http://127.0.0.1:" + server.getAddress().getPort(), serviceToken);
    }

    private void recordRequest(HttpExchange exchange) throws IOException {
        path.set(exchange.getRequestURI().getPath());
        token.set(exchange.getRequestHeaders().getFirst("X-Service-Token"));
        requestBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
        respond(exchange, 200, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", validDocx());
    }

    private static void respond(HttpExchange exchange, int status, String contentType, byte[] body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.sendResponseHeaders(status, body.length);
        try (var output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    private static byte[] validDocx() {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
                zip.putNextEntry(new ZipEntry("[Content_Types].xml"));
                zip.write("<Types/>".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
                zip.putNextEntry(new ZipEntry("word/document.xml"));
                zip.write("<w:document/>".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
            return bytes.toByteArray();
        } catch (IOException error) {
            throw new AssertionError(error);
        }
    }

    private record ResponseCase(String contentType, byte[] body) {}
}
