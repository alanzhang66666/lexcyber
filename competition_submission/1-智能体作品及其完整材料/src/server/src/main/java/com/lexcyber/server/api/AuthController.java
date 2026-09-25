package com.lexcyber.server.api;

import com.lexcyber.server.auth.AuthLogin;
import com.lexcyber.server.auth.AuthRegister;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.auth.SessionView;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/auth")
public class AuthController {
    private final AuthService auth;

    public AuthController(AuthService auth) {
        this.auth = auth;
    }

    @PostMapping("/register")
    public ResponseEntity<SessionView> register(@Valid @RequestBody AuthRegister request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(auth.register(request));
    }

    @PostMapping("/login")
    public SessionView login(@Valid @RequestBody AuthLogin request) {
        return auth.login(request);
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(@RequestHeader(value = "Authorization", required = false) String authorization) {
        auth.logout(authorization);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/session")
    public SessionView session(@RequestHeader(value = "Authorization", required = false) String authorization) {
        return auth.current(authorization);
    }
}
