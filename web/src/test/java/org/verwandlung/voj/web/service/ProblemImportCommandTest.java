package org.verwandlung.voj.web.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.file.Files;
import java.nio.file.Path;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import org.verwandlung.voj.web.model.ProblemImportReport;
import org.verwandlung.voj.web.model.ProblemImportResult;

class ProblemImportCommandTest {
  @Test
  void importsMappedPlanAndReportsEveryAction() throws Exception {
    ProblemImportService service = mock(ProblemImportService.class);
    when(service.importProblem(any()))
        .thenReturn(new ProblemImportResult(ProblemImportResult.Action.CREATED, 456))
        .thenReturn(new ProblemImportResult(ProblemImportResult.Action.UPDATED, 457))
        .thenReturn(new ProblemImportResult(ProblemImportResult.Action.SKIPPED, 458));
    ProblemImportCommand command = new ProblemImportCommand(service);
    Path mapping = mappingFile();
    Path plan = planFile("hydro", "authorization-42", "P00456", 0, mapping);

    ProblemImportReport report = command.importPlan(plan, mapping);

    assertEquals(1, report.created());
    assertEquals(1, report.updated());
    assertEquals(1, report.skipped());
    assertEquals(3, report.results().size());
    verify(service, times(3)).importProblem(any());
  }

  @Test
  void acceptsVerifiedManualUserProvidedPlan() throws Exception {
    ProblemImportService service = mock(ProblemImportService.class);
    when(service.importProblem(any()))
        .thenReturn(new ProblemImportResult(ProblemImportResult.Action.CREATED, 278));
    ProblemImportCommand command = new ProblemImportCommand(service);
    Path mapping = mappingFile();
    Path plan = planFile("manual", "user-provided:chat", "P00278", 0, mapping);

    ProblemImportReport report = command.importPlan(plan, mapping);

    assertEquals(3, report.created());
    verify(service, times(3)).importProblem(any());
  }

  @Test
  void rejectsIncompleteTamperedOrMismatchedMappingBeforeImport() throws Exception {
    ProblemImportService service = mock(ProblemImportService.class);
    ProblemImportCommand command = new ProblemImportCommand(service);
    Path mapping = mappingFile();

    Path rejected = planFile("hydro", "authorization-42", "P00456", 1, mapping);
    assertThrows(IllegalArgumentException.class, () -> command.importPlan(rejected, mapping));

    ObjectMapper mapper = new ObjectMapper();
    Path tampered = planFile("hydro", "authorization-42", "P00456", 0, mapping);
    ObjectNode tamperedNode = (ObjectNode) mapper.readTree(tampered.toFile());
    ((ObjectNode) tamperedNode.path("accepted").get(0)).put("title", "tampered");
    mapper.writeValue(tampered.toFile(), tamperedNode);
    assertThrows(IllegalArgumentException.class, () -> command.importPlan(tampered, mapping));

    Path redirected = planFile("hydro", "authorization-42", "P00456", 0, mapping);
    ObjectNode redirectedNode = (ObjectNode) mapper.readTree(redirected.toFile());
    ((ObjectNode) redirectedNode.path("accepted").get(0)).put("targetProblemId", 9999);
    redirectedNode.put("planSha256", ProblemImportCommand.planDigest(redirectedNode));
    mapper.writeValue(redirected.toFile(), redirectedNode);
    assertThrows(IllegalArgumentException.class, () -> command.importPlan(redirected, mapping));

    Path otherMapping = Files.createTempFile("problem-mapping", ".json");
    Files.writeString(
        otherMapping,
        "{\"schemaVersion\":1,\"sourceIdRange\":\"P00000-P10000\",\"targetProblemIdStart\":1}");
    assertThrows(IllegalArgumentException.class, () -> command.importPlan(redirected, otherMapping));
    verify(service, times(0)).importProblem(any());
  }

  @Test
  void acceptsMappedBoundaryIdsAndRejectsMalformedIds() throws Exception {
    for (String sourceId : java.util.List.of("P00000", "P10000")) {
      ProblemImportService service = mock(ProblemImportService.class);
      when(service.importProblem(any()))
          .thenReturn(new ProblemImportResult(ProblemImportResult.Action.CREATED, 1));
      ProblemImportCommand command = new ProblemImportCommand(service);
      Path mapping = mappingFile();

      command.importPlan(planFile("hydro", "authorization-42", sourceId, 0, mapping), mapping);

      verify(service, times(3)).importProblem(any());
    }

    for (String sourceId : java.util.List.of("P10001", "P0000", "P100000", "Q00000")) {
      ProblemImportService service = mock(ProblemImportService.class);
      ProblemImportCommand command = new ProblemImportCommand(service);
      Path mapping = mappingFile();
      Path plan = planFile("hydro", "authorization-42", sourceId, 0, mapping);

      assertThrows(IllegalArgumentException.class, () -> command.importPlan(plan, mapping));
      verify(service, times(0)).importProblem(any());
    }
  }

  private Path mappingFile() throws Exception {
    Path path = Files.createTempFile("problem-mapping", ".json");
    Files.writeString(
        path,
        "{\"schemaVersion\":1,\"sourceIdRange\":\"P00000-P10000\",\"targetProblemIdStart\":0}");
    return path;
  }

  private Path planFile(
      String sourceSystem,
      String authorizationRef,
      String firstSourceId,
      int rejectedCount,
      Path mappingPath)
      throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    ProblemIdMapping mapping = ProblemIdMapping.load(mappingPath, mapper);
    ArrayNode accepted = mapper.createArrayNode();
    long firstNumber = validSourceNumber(firstSourceId);
    long direction = firstNumber > 9998 ? -1 : 1;
    for (int index = 0; index < 3; index++) {
      long sourceNumber = firstNumber + direction * index;
      String sourceId =
          firstSourceId.matches("P\\d{5}")
              ? String.format("P%05d", sourceNumber)
              : firstSourceId;
      ObjectNode problem = mapper.createObjectNode();
      problem.put("sourceSystem", sourceSystem);
      problem.put("sourceDomain", "manual".equals(sourceSystem) ? "user-provided" : "hwod_oj");
      problem.put("sourceId", sourceId);
      problem.put("targetProblemId", sourceId.matches("P\\d{5}") ? sourceNumber : 0);
      problem.put("contentSha256", "a".repeat(64));
      problem.put("title", "Synthetic");
      problem.put("timeLimitMs", 1000);
      problem.put("memoryLimitKb", 262144);
      problem.put("description", "Description");
      problem.put("inputFormat", "Input");
      problem.put("outputFormat", "Output");
      problem.put("sampleInput", "1");
      problem.put("sampleOutput", "2");
      problem.put("hint", "");
      problem.put("judgeMode", "default");
      problem.put("authorizationRef", authorizationRef);
      problem.put("workflowState", "human-approved");
      problem.putObject("verification").put("passed", true).put("reportSha256", "b".repeat(64));
      problem.put("exactlyMatch", true);
      problem.putArray("tags").add("模拟");
      problem.putArray("testCases").addObject().put("input", "1").put("output", "2");
      accepted.add(problem);
    }
    ObjectNode plan = mapper.createObjectNode();
    plan.put("schemaVersion", 2);
    plan.put("sourceSystem", sourceSystem);
    plan.put("authorizationRef", authorizationRef);
    plan.put("mappingSha256", mapping.sha256());
    plan.put("expectedCount", 3);
    plan.put("acceptedCount", 3);
    plan.put("rejectedCount", rejectedCount);
    plan.set("accepted", accepted);
    plan.putArray("rejected");
    plan.put("planSha256", ProblemImportCommand.planDigest(plan));
    Path path = Files.createTempFile("problem-import-plan", ".json");
    mapper.writeValue(path.toFile(), plan);
    return path;
  }

  private long validSourceNumber(String sourceId) {
    return sourceId.matches("P\\d{5}") ? Long.parseLong(sourceId.substring(1)) : 0;
  }
}
