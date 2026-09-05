package com.lexcyber.server.domain;

import java.util.List;
import java.util.UUID;

public record ResultRef(UUID resultId, int version, String type, String contentHash, List<SourceRef> sourceRefs) {
}
