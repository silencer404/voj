package org.verwandlung.voj.web.service;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

final class ProblemIdMapping {
  static ProblemIdMapping load(Path path, ObjectMapper mapper) throws IOException {
    JsonNode value = mapper.readTree(path.toFile());
    if (!value.isObject()
        || !fields(value).equals(Set.of("schemaVersion", "sourceIdRange", "targetProblemIdStart"))
        || value.path("schemaVersion").asInt(-1) != 1
        || !"P00000-P10000".equals(value.path("sourceIdRange").asText())
        || !value.path("targetProblemIdStart").isIntegralNumber()
        || value.path("targetProblemIdStart").asInt(-1) != 0) {
      throw new IllegalArgumentException("unsupported problem mapping policy");
    }
    return new ProblemIdMapping(value, ProblemImportCommand.digest(value));
  }

  long targetProblemId(String sourceId) {
    Matcher matcher = SOURCE_ID.matcher(sourceId);
    if (!matcher.matches()) {
      throw new IllegalArgumentException("invalid source id");
    }
    long value = Long.parseLong(matcher.group(1));
    if (value > 10000) {
      throw new IllegalArgumentException("source id outside mapping");
    }
    return value;
  }

  String sha256() {
    return sha256;
  }

  private static Set<String> fields(JsonNode value) {
    java.util.HashSet<String> names = new java.util.HashSet<>();
    value.fieldNames().forEachRemaining(names::add);
    return names;
  }

  private ProblemIdMapping(JsonNode value, String sha256) {
    this.value = value;
    this.sha256 = sha256;
  }

  private static final Pattern SOURCE_ID = Pattern.compile("P(\\d{5})");
  @SuppressWarnings("unused")
  private final JsonNode value;
  private final String sha256;
}
