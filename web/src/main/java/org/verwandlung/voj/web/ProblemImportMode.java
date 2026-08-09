package org.verwandlung.voj.web;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

final class ProblemImportMode {
  private static final String PLAN_PREFIX = "--voj.problem-import-plan=";
  private static final String MAPPING_PREFIX = "--voj.problem-mapping=";

  static boolean requested(String[] args) {
    for (String argument : args) {
      if (argument.startsWith(PLAN_PREFIX)) {
        return true;
      }
    }
    return false;
  }

  static int successExitCode() {
    return 0;
  }

  static Path planPath(String[] args) {
    List<String> values = new ArrayList<>();
    for (String argument : args) {
      if (argument.startsWith(PLAN_PREFIX)) {
        values.add(argument.substring(PLAN_PREFIX.length()));
      }
    }
    if (values.size() != 1 || values.get(0).isBlank()) {
      throw new IllegalArgumentException("exactly one non-empty problem import plan is required");
    }
    return Path.of(values.get(0));
  }

  static Path mappingPath(String[] args) {
    List<String> values = new ArrayList<>();
    for (String argument : args) {
      if (argument.startsWith(MAPPING_PREFIX)) {
        values.add(argument.substring(MAPPING_PREFIX.length()));
      }
    }
    if (values.size() != 1 || values.get(0).isBlank()) {
      throw new IllegalArgumentException("exactly one non-empty problem mapping is required");
    }
    return Path.of(values.get(0));
  }

  private ProblemImportMode() {}
}
