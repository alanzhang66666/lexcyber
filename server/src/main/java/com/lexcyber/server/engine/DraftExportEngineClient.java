package com.lexcyber.server.engine;

import com.lexcyber.server.api.ApiException;
import java.net.http.HttpClient;
import java.util.zip.ZipFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/** Token-protected Engine client for rendering one immutable draft version. */
@Component
public class DraftExportEngineClient {
    private final RestClient client;
    private final String token;

    public DraftExportEngineClient(RestClient.Builder builder,
                                   @Value("${engine.base-url}") String baseUrl,
                                   @Value("${engine.service-token}") String token) {
        // The cleartext Uvicorn endpoint does not support HTTP/2 (h2c) upgrade.
        var requestFactory = new JdkClientHttpRequestFactory(
                HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                        .connectTimeout(Duration.ofSeconds(5)).build());
        requestFactory.setReadTimeout(Duration.ofSeconds(30));
        this.client = builder.baseUrl(baseUrl).requestFactory(requestFactory).build();
        this.token = token;
    }

    public byte[] render(Map<String, Object> payload) {
        try {
            var response = client.post()
                    .uri("/internal/v1/draft-exports/docx")
                    .header("X-Service-Token", token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(payload)
                    .retrieve()
                    .toEntity(byte[].class);
            MediaType type = response.getHeaders().getContentType();
            byte[] bytes = response.getBody();
            if (type == null || !MediaType.parseMediaType(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document").isCompatibleWith(type)
                    || !isDocx(bytes)) {
                throw unavailable("engine returned an invalid DOCX");
            }
            if (bytes == null || bytes.length == 0) {
                throw unavailable("engine returned an empty DOCX");
            }
            return bytes;
        } catch (RestClientResponseException ex) {
            if (ex.getStatusCode().value() == 409 || ex.getStatusCode().value() == 422) {
                throw new ApiException(org.springframework.http.HttpStatus.CONFLICT,
                        "DRAFT_EXPORT_BLOCKED", "文书内容不满足导出条件", ex);
            }
            throw unavailable("engine DOCX export failed", ex);
        } catch (ApiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw unavailable("engine DOCX export unavailable", ex);
        }
    }

    private static boolean isDocx(byte[] bytes) {
        if (bytes == null || bytes.length < 4 || bytes[0] != 'P' || bytes[1] != 'K') return false;
        Path temporary = null;
        try {
            temporary = Files.createTempFile("lexcyber-draft-", ".docx");
            Files.write(temporary, bytes);
            try (ZipFile zip = new ZipFile(temporary.toFile())) {
                return zip.getEntry("[Content_Types].xml") != null
                        && zip.getEntry("word/document.xml") != null;
            }
        } catch (Exception ex) {
            return false;
        } finally {
            if (temporary != null) {
                try { Files.deleteIfExists(temporary); } catch (Exception ignored) { }
            }
        }
    }

    private static ApiException unavailable(String message) {
        return unavailable(message, null);
    }

    private static ApiException unavailable(String message, Throwable cause) {
        return new ApiException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
                "DRAFT_EXPORT_UNAVAILABLE", message, cause);
    }
}
