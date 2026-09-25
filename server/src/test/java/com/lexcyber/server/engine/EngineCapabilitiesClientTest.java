package com.lexcyber.server.engine;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

/** INV-GATE-002：能力声明不可达时必须 fail-closed（模块不可用），不得放行派发。 */
class EngineCapabilitiesClientTest {

    @Test
    void unavailableEngineClosesGate() {
        EngineCapabilitiesClient client = new EngineCapabilitiesClient(
                RestClient.builder(), "http://127.0.0.1:1", "token");
        assertNull(client.capabilities());
        assertFalse(client.moduleAvailable("compliance"));
        assertFalse(client.moduleAvailable("conviction"));
        assertFalse(client.moduleAvailable("sentencing"));
    }

    @Test
    void malformedModuleIsNotAvailable() {
        EngineCapabilitiesClient client = new EngineCapabilitiesClient(
                RestClient.builder(), "http://127.0.0.1:1", "token");
        assertFalse(client.moduleAvailable("nonexistent-module"));
    }
}
