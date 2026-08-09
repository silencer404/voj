package org.verwandlung.voj.web.model;

public record ProblemImportResult(Action action, long problemId) {
  public enum Action {
    CREATED,
    UPDATED,
    SKIPPED
  }
}
