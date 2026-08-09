package org.verwandlung.voj.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;

import org.junit.jupiter.api.Test;

class ProblemImportModeTest {
  @Test
  void recognizesExplicitSinglePlanArgument() {
    String[] args = {
      "--spring.main.banner-mode=off",
      "--voj.problem-import-plan=/tmp/plan.json",
      "--voj.problem-mapping=/tmp/problem_mapping.json"
    };

    assertTrue(ProblemImportMode.requested(args));
    assertEquals(Path.of("/tmp/plan.json"), ProblemImportMode.planPath(args));
    assertEquals(
        Path.of("/tmp/problem_mapping.json"), ProblemImportMode.mappingPath(args));
  }

  @Test
  void leavesNormalWebStartupUntouched() {
    String[] args = {"--server.port=8080"};

    assertFalse(ProblemImportMode.requested(args));
  }

  @Test
  void returnsSuccessfulProcessExitCode() {
    assertEquals(0, ProblemImportMode.successExitCode());
  }

  @Test
  void rejectsBlankOrRepeatedPlanArguments() {
    assertThrows(
        IllegalArgumentException.class,
        () -> ProblemImportMode.planPath(new String[] {"--voj.problem-import-plan="}));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            ProblemImportMode.planPath(
                new String[] {
                  "--voj.problem-import-plan=/tmp/a.json",
                  "--voj.problem-import-plan=/tmp/b.json"
                }));
  }

  @Test
  void rejectsBlankOrRepeatedMappingArguments() {
    assertThrows(
        IllegalArgumentException.class,
        () -> ProblemImportMode.mappingPath(new String[] {"--voj.problem-mapping="}));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            ProblemImportMode.mappingPath(
                new String[] {
                  "--voj.problem-mapping=/tmp/a.json",
                  "--voj.problem-mapping=/tmp/b.json"
                }));
  }
}
