package org.verwandlung.voj.web.service;

import java.io.IOException;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import org.verwandlung.voj.web.model.ProblemImportReport;
import org.verwandlung.voj.web.model.ProblemImportRequest;
import org.verwandlung.voj.web.model.ProblemImportResult;

@Component
public class ProblemImportCommand {
  public ProblemImportCommand(ProblemImportService importService) {
    this.objectMapper = new ObjectMapper();
    this.importService = importService;
  }

  public String toJson(ProblemImportReport report) throws IOException {
    return objectMapper.writeValueAsString(report);
  }

  @Transactional
  public ProblemImportReport importPlan(Path planPath, Path mappingPath) throws IOException {
    JsonNode plan = objectMapper.readTree(planPath.toFile());
    ProblemIdMapping mapping = ProblemIdMapping.load(mappingPath, objectMapper);
    validatePlan(plan, mapping);
    JsonNode accepted = plan.path("accepted");

    List<ProblemImportRequest> requests = new ArrayList<>();
    Set<Long> targetIds = new HashSet<>();
    Set<String> provenances = new HashSet<>();
    for (JsonNode problem : accepted) {
      validateAcceptedProblem(
          problem,
          plan.path("sourceSystem").asText(),
          plan.path("authorizationRef").asText(),
          mapping);
      ProblemImportRequest request = objectMapper.treeToValue(problem, ProblemImportRequest.class);
      String provenance =
          request.sourceSystem() + "\0" + request.sourceDomain() + "\0" + request.sourceId();
      if (!targetIds.add(request.targetProblemId()) || !provenances.add(provenance)) {
        throw new IllegalArgumentException("duplicate mapped problem in import plan");
      }
      importService.validate(request);
      requests.add(request);
    }

    List<ProblemImportResult> results = new ArrayList<>();
    int created = 0;
    int updated = 0;
    int skipped = 0;
    for (ProblemImportRequest request : requests) {
      ProblemImportResult result = importService.importProblem(request);
      results.add(result);
      switch (result.action()) {
        case CREATED -> created++;
        case UPDATED -> updated++;
        case SKIPPED -> skipped++;
      }
    }
    return new ProblemImportReport(created, updated, skipped, List.copyOf(results));
  }

  static String digest(JsonNode value) {
    try {
      byte[] canonical = CANONICAL_MAPPER.writeValueAsBytes(canonicalize(value));
      return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical));
    } catch (IOException | NoSuchAlgorithmException error) {
      throw new IllegalStateException("cannot compute digest", error);
    }
  }

  static String planDigest(JsonNode plan) {
    ObjectNode withoutDigest = plan.deepCopy();
    withoutDigest.remove("planSha256");
    return digest(withoutDigest);
  }

  private void validatePlan(JsonNode plan, ProblemIdMapping mapping) {
    JsonNode accepted = plan.path("accepted");
    JsonNode rejected = plan.path("rejected");
    String authorizationRef = plan.path("authorizationRef").asText();
    String sourceSystem = plan.path("sourceSystem").asText();
    if (plan.path("schemaVersion").asInt(-1) != 2
        || !("hydro".equals(sourceSystem) || "manual".equals(sourceSystem))
        || !mapping.sha256().equals(plan.path("mappingSha256").asText())
        || authorizationRef.isBlank()
        || !accepted.isArray()
        || !rejected.isArray()
        || plan.path("rejectedCount").asInt(-1) != rejected.size()
        || plan.path("rejectedCount").asInt(-1) != 0
        || plan.path("acceptedCount").asInt(-1) != accepted.size()
        || plan.path("expectedCount").asInt(-1) != accepted.size() + rejected.size()
        || !planDigest(plan).equals(plan.path("planSha256").asText())) {
      throw new IllegalArgumentException("invalid or incomplete import plan");
    }
  }

  private void validateAcceptedProblem(
      JsonNode problem,
      String sourceSystem,
      String authorizationRef,
      ProblemIdMapping mapping) {
    String sourceId = problem.path("sourceId").asText();
    int sourceNumber;
    try {
      sourceNumber = Integer.parseInt(sourceId.substring(1));
    } catch (RuntimeException error) {
      throw new IllegalArgumentException("invalid source id", error);
    }
    boolean hydro = "hydro".equals(problem.path("sourceSystem").asText());
    boolean manual = "manual".equals(problem.path("sourceSystem").asText());
    boolean validSource =
        (hydro
                && "hwod_oj".equals(problem.path("sourceDomain").asText())
                && sourceNumber >= 0
                && sourceNumber <= 10000)
            || (manual
                && "user-provided".equals(problem.path("sourceDomain").asText())
                && authorizationRef.startsWith("user-provided:"));
    if (!validSource
        || !sourceSystem.equals(problem.path("sourceSystem").asText())
        || !sourceId.matches("P\\d{5}")
        || problem.path("targetProblemId").isMissingNode()
        || problem.path("targetProblemId").asLong(-1) != mapping.targetProblemId(sourceId)
        || !authorizationRef.equals(problem.path("authorizationRef").asText())
        || !"human-approved".equals(problem.path("workflowState").asText())
        || !problem.path("verification").path("passed").asBoolean(false)
        || !problem.path("verification").path("reportSha256").asText().matches("[a-f0-9]{64}")
        || !List.of("default", "exact", "standard").contains(problem.path("judgeMode").asText())
        || !problem.path("exactlyMatch").asBoolean(false)) {
      throw new IllegalArgumentException("accepted problem failed import gates");
    }
  }

  private static JsonNode canonicalize(JsonNode node) {
    if (node.isObject()) {
      ObjectNode sorted = CANONICAL_MAPPER.createObjectNode();
      List<String> names = new ArrayList<>();
      node.fieldNames().forEachRemaining(names::add);
      names.sort(Comparator.naturalOrder());
      for (String name : names) {
        sorted.set(name, canonicalize(node.get(name)));
      }
      return sorted;
    }
    if (node.isArray()) {
      ArrayNode array = CANONICAL_MAPPER.createArrayNode();
      node.forEach(value -> array.add(canonicalize(value)));
      return array;
    }
    return node;
  }

  private static final ObjectMapper CANONICAL_MAPPER = new ObjectMapper();
  private final ObjectMapper objectMapper;
  private final ProblemImportService importService;
}
