package com.lexcyber.server.engine;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.lexcyber.server.api.ApiException;
import com.lexcyber.server.domain.ExternalDependencyValidity;
import java.security.SecureRandom;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * Registry verification boundary.  The application never reads engine tables;
 * it holds a transaction-scoped shared barrier and asks the Engine to verify
 * the frozen dependency tuples on that same PostgreSQL connection.
 */
@Component
public class EngineRegistryClient {
    public static final long REGISTRY_BARRIER = 5495895966559126866L;
    private static final int MAX_DEPENDENCIES = 4096;
    private static final SecureRandom RANDOM = new SecureRandom();
    private final RestClient client;
    private final String token;
    private final boolean enforceTransaction;

    /** Compatibility constructor for isolated unit tests. It fails closed. */
    public EngineRegistryClient() {
        this.client = null;
        this.token = null;
        this.enforceTransaction = false;
    }

    @Autowired
    public EngineRegistryClient(RestClient.Builder builder,
                                @Value("${engine.base-url}") String baseUrl,
                                @Value("${engine.service-token}") String token) {
        var requestFactory = new JdkClientHttpRequestFactory(
                HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                        .connectTimeout(Duration.ofSeconds(5)).build());
        requestFactory.setReadTimeout(Duration.ofSeconds(10));
        this.client = builder.clone().baseUrl(baseUrl).requestFactory(requestFactory).build();
        this.token = token;
        this.enforceTransaction = true;
    }

    public void requireValid(JdbcTemplate jdbc, UUID artifactVersionId) {
        if (enforceTransaction && !TransactionSynchronizationManager.isActualTransactionActive()) {
            throw unavailable("registry verification requires an active transaction", null);
        }
        lockBarrier(jdbc);
        List<ExternalDependencyValidity> dependencies;
        try {
            dependencies = dependenciesFor(jdbc, artifactVersionId);
        } catch (IllegalArgumentException invalid) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "外部依赖快照包含空版本，操作被阻断", invalid);
        }
        if (dependencies.isEmpty()) return; // legacy artifacts remain readable and archivable
        for (int from = 0; from < dependencies.size(); from += MAX_DEPENDENCIES) {
            int to = Math.min(from + MAX_DEPENDENCIES, dependencies.size());
            verifyChunk(jdbc, dependencies.subList(from, to));
        }
    }

    /** Acquire before any case/head/review lock on a gated write path. */
    public void lockBarrier(JdbcTemplate jdbc) {
        if (enforceTransaction && !TransactionSynchronizationManager.isActualTransactionActive()) {
            throw unavailable("registry barrier requires an active transaction", null);
        }
        jdbc.queryForList("SELECT pg_advisory_xact_lock_shared(?)", (Object) REGISTRY_BARRIER);
    }

    public List<ExternalDependencyValidity> dependenciesFor(JdbcTemplate jdbc, UUID artifactVersionId) {
        return jdbc.query("""
                WITH RECURSIVE closure(artifact_version_id) AS (
                    SELECT ?::uuid
                    UNION
                    SELECT d.depends_on_artifact_version_id
                    FROM app.artifact_artifact_dependency d
                    JOIN closure c ON c.artifact_version_id = d.artifact_version_id
                )
                SELECT DISTINCT e.dependency_kind, e.dependency_key, e.dependency_version
                FROM closure c
                JOIN app.artifact_external_dependency e
                  ON e.artifact_version_id = c.artifact_version_id
                ORDER BY e.dependency_kind, e.dependency_key, e.dependency_version
                """, (rs, ignored) -> new ExternalDependencyValidity(
                        rs.getString(1), rs.getString(2), rs.getString(3)), artifactVersionId);
    }

    private void verifyChunk(JdbcTemplate jdbc, List<ExternalDependencyValidity> dependencies) {
        if (client == null) {
            throw unavailable("Engine registry client is not configured", null);
        }
        Integer backendPid = jdbc.queryForObject("SELECT pg_backend_pid()", Integer.class);
        long challenge;
        do { challenge = RANDOM.nextLong(); } while (challenge == REGISTRY_BARRIER);
        jdbc.queryForList("SELECT pg_advisory_xact_lock_shared(?)", (Object) challenge);
        RegistryResponse response;
        try {
            response = client.post().uri("/internal/v1/registry/verify-dependencies")
                    .header("X-Service-Token", token)
                    .body(new RegistryRequest(new Coordination(backendPid, Long.toString(challenge)), dependencies))
                    .retrieve().body(RegistryResponse.class);
        } catch (Exception ex) {
            throw unavailable("Engine registry verification unavailable", ex);
        }
        if (response == null || response.invalidDependencies() == null
                || !response.valid() && response.invalidDependencies().isEmpty()
                || response.valid() && !response.invalidDependencies().isEmpty()) {
            throw unavailable("Malformed Engine registry verification response", null);
        }
        if (!response.valid()) {
            throw new ApiException(HttpStatus.CONFLICT, "DEPENDENCY_STALE",
                    "外部法源、规则或模板已失效，操作被阻断");
        }
    }

    private static ApiException unavailable(String message, Throwable cause) {
        return cause == null
                ? new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "REGISTRY_VERIFICATION_UNAVAILABLE", message)
                : new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "REGISTRY_VERIFICATION_UNAVAILABLE", message, cause);
    }

    public record Coordination(int backendPid, String challenge) {}
    public record RegistryRequest(Coordination coordination,
                                  List<ExternalDependencyValidity> dependencies) {}
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record RegistryResponse(boolean valid,
            @JsonProperty("invalidDependencies") List<ExternalDependencyValidity.InvalidDependency> invalidDependencies) {}
}
