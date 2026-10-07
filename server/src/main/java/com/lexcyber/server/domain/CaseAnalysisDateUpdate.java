package com.lexcyber.server.domain;

import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

public record CaseAnalysisDateUpdate(@NotNull LocalDate asOfDate, LocalDate expectedAsOfDate) {}
