package com.lexcyber.server.domain;

import com.lexcyber.server.api.ApiException;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * v1.3 §4.9 — 统一幂等记录（principal_id, idempotency_key）。
 * 记录必须与目标资源创建在同一事务内；request hash 不同 → 409。
 */
@Service
public class IdempotencyService {
    private final JdbcTemplate jdbc;

    public IdempotencyService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public enum Outcome { PROCEED, REPLAY }

    public record Claim(Outcome outcome, UUID resourceId, int responseStatus) {
        public boolean replay() {
            return outcome == Outcome.REPLAY;
        }
    }

    /**
     * 认领幂等键：首次 → PROCEED（调用方完成资源创建后必须调 record）；
     * 同 hash 重放 → REPLAY + 既有 resourceId；不同 hash → 409。
     */
    public Claim claim(UUID principalId, String key, String requestHash) {
        jdbc.update("""
                INSERT INTO app.idempotency_record(
                    principal_id, idempotency_key, request_hash, resource_type, resource_id, response_status)
                VALUES (?, ?, ?, 'pending', '00000000-0000-0000-0000-000000000000', 0)
                ON CONFLICT (principal_id, idempotency_key) DO NOTHING
                """, principalId, key, requestHash);
        Map<String, Object> row = jdbc.queryForMap("""
                SELECT request_hash, resource_type, resource_id, response_status
                FROM app.idempotency_record
                WHERE principal_id = ? AND idempotency_key = ? FOR UPDATE
                """, principalId, key);
        if (!requestHash.equals(row.get("request_hash"))) {
            throw new ApiException(HttpStatus.CONFLICT,
                    "IDEMPOTENCY_CONFLICT",
                    "相同幂等键已用于不同请求");
        }
        if ("pending".equals(row.get("resource_type"))) {
            return new Claim(Outcome.PROCEED, null, 0);
        }
        return new Claim(Outcome.REPLAY, (UUID) row.get("resource_id"),
                ((Number) row.get("response_status")).intValue());
    }

    /** 资源创建成功后登记（同事务）。 */
    public void record(UUID principalId, String key, String resourceType, UUID resourceId, int status) {
        jdbc.update("""
                UPDATE app.idempotency_record
                SET resource_type = ?, resource_id = ?, response_status = ?
                WHERE principal_id = ? AND idempotency_key = ?
                """, resourceType, resourceId, status, principalId, key);
    }
}
