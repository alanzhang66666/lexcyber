package com.lexcyber.server.domain;

import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class ExternalDependencyValidityTest {
    @Test
    void dependencyTupleRejectsMissingVersion() {
        assertThrows(IllegalArgumentException.class,
                () -> new ExternalDependencyValidity("rule", "r-1", ""));
    }

    @Test
    void validResponseCannotCarryInvalidEntries() {
        ExternalDependencyValidity.InvalidDependency invalid =
                new ExternalDependencyValidity.InvalidDependency("rule", "r-1", "v1", "revoked");
        assertThrows(IllegalArgumentException.class,
                () -> new ExternalDependencyValidity.Verification(true, List.of(invalid)));
    }

    @Test
    void nullInvalidListIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new ExternalDependencyValidity.Verification(true, null));
    }
}
