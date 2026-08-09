package org.verwandlung.voj.web.model;

import java.util.List;

public record ProblemImportReport(
    int created, int updated, int skipped, List<ProblemImportResult> results) {}
