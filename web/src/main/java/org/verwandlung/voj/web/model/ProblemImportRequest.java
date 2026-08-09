package org.verwandlung.voj.web.model;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProblemImportRequest(
    String sourceSystem,
    String sourceDomain,
    String sourceId,
    Long targetProblemId,
    String contentSha256,
    String title,
    int timeLimitMs,
    int memoryLimitKb,
    String description,
    String inputFormat,
    String outputFormat,
    String sampleInput,
    String sampleOutput,
    String hint,
    boolean exactlyMatch,
    List<String> tags,
    List<ProblemImportTestCase> testCases) {}
