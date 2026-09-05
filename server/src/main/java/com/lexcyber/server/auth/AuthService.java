package com.lexcyber.server.auth;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {
    private static final Duration SESSION_TTL = Duration.ofDays(7);
    private final JdbcTemplate jdbc;

    public AuthService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean hasBearer(String authorization) {
        return AuthTokens.parseBearer(authorization).isPresent();
    }

    @Transactional
    public SessionView register(AuthRegister request) {
        String username = request.username().trim();
        String displayName = request.displayName() == null || request.displayName().isBlank()
                ? username
                : request.displayName().trim();
        UUID accountId = UUID.randomUUID();
        try {
            jdbc.update("""
                    INSERT INTO app.accounts(id, username, username_normalized, display_name, password_hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    accountId, username, username.toLowerCase(Locale.ROOT), displayName, PasswordHasher.hash(request.password()));
        } catch (DuplicateKeyException duplicate) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "account already exists", duplicate);
        }
        return issueSession(accountId, username, displayName);
    }

    @Transactional
    public SessionView login(AuthLogin request) {
        String normalized = request.username().trim().toLowerCase(Locale.ROOT);
        AccountRow account;
        try {
            account = jdbc.queryForObject("""
                    SELECT id, username, display_name, password_hash
                    FROM app.accounts
                    WHERE username_normalized = ?
                    """,
                    (rs, ignored) -> new AccountRow(
                            rs.getObject("id", UUID.class),
                            rs.getString("username"),
                            rs.getString("display_name"),
                            rs.getString("password_hash")),
                    normalized);
        } catch (EmptyResultDataAccessException missing) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid credentials", missing);
        }
        if (account == null || !PasswordHasher.matches(request.password(), account.passwordHash())) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid credentials");
        }
        return issueSession(account.id(), account.username(), account.displayName());
    }

    @Transactional
    public void logout(String authorization) {
        AuthTokens.parseBearer(authorization).ifPresent(token ->
                jdbc.update("DELETE FROM app.auth_sessions WHERE token_hash = ?", AuthTokens.sha256Hex(token)));
    }

    @Transactional(readOnly = true)
    public SessionView current(String authorization) {
        ResolvedSession session = requireSession(authorization);
        return new SessionView(null, session.username(), session.displayName(), session.expiresAt());
    }

    @Transactional(readOnly = true)
    public Optional<AuthAccount> resolve(String authorization) {
        return AuthTokens.parseBearer(authorization).flatMap(this::findValid).map(ResolvedSession::account);
    }

    public AuthAccount require(String authorization) {
        return requireSession(authorization).account();
    }

    private ResolvedSession requireSession(String authorization) {
        return AuthTokens.parseBearer(authorization)
                .flatMap(this::findValid)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session required"));
    }

    private Optional<ResolvedSession> findValid(String token) {
        return jdbc.query("""
                SELECT a.id, a.username, a.display_name, s.expires_at
                FROM app.auth_sessions s
                JOIN app.accounts a ON a.id = s.account_id
                WHERE s.token_hash = ? AND s.expires_at > now()
                """,
                (rs, ignored) -> new ResolvedSession(
                        new AuthAccount(rs.getObject("id", UUID.class), rs.getString("username"), rs.getString("display_name")),
                        rs.getObject("expires_at", OffsetDateTime.class)),
                AuthTokens.sha256Hex(token)).stream().findFirst();
    }

    private SessionView issueSession(UUID accountId, String username, String displayName) {
        String token = AuthTokens.randomToken();
        OffsetDateTime expiresAt = OffsetDateTime.now().plus(SESSION_TTL);
        jdbc.update("""
                INSERT INTO app.auth_sessions(id, account_id, token_hash, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                UUID.randomUUID(), accountId, AuthTokens.sha256Hex(token), expiresAt);
        return new SessionView(token, username, displayName, expiresAt);
    }

    private record AccountRow(UUID id, String username, String displayName, String passwordHash) {
    }

    private record ResolvedSession(AuthAccount account, OffsetDateTime expiresAt) {
        String username() {
            return account.username();
        }

        String displayName() {
            return account.displayName();
        }
    }
}
