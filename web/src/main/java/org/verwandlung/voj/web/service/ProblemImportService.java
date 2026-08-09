package org.verwandlung.voj.web.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import org.verwandlung.voj.web.mapper.CheckpointMapper;
import org.verwandlung.voj.web.mapper.ProblemCategoryMapper;
import org.verwandlung.voj.web.mapper.ProblemMapper;
import org.verwandlung.voj.web.mapper.ProblemTagMapper;
import org.verwandlung.voj.web.model.Checkpoint;
import org.verwandlung.voj.web.model.Problem;
import org.verwandlung.voj.web.model.ProblemCategory;
import org.verwandlung.voj.web.model.ProblemDifficulty;
import org.verwandlung.voj.web.model.ProblemImportRequest;
import org.verwandlung.voj.web.model.ProblemImportResult;
import org.verwandlung.voj.web.model.ProblemImportTestCase;
import org.verwandlung.voj.web.model.ProblemTag;
import org.verwandlung.voj.web.model.PublicationStatus;
import org.verwandlung.voj.web.util.SlugifyUtils;

@Service
@Transactional
public class ProblemImportService {
  public ProblemImportService(
      ProblemMapper problemMapper,
      CheckpointMapper checkpointMapper,
      ProblemCategoryMapper categoryMapper,
      ProblemTagMapper tagMapper) {
    this.problemMapper = problemMapper;
    this.checkpointMapper = checkpointMapper;
    this.categoryMapper = categoryMapper;
    this.tagMapper = tagMapper;
  }

  public ProblemImportResult importProblem(ProblemImportRequest request) {
    validate(request);
    Problem existing =
        problemMapper.getProblemUsingProvenanceForUpdate(
            request.sourceSystem(), request.sourceDomain(), request.sourceId());
    Problem target = problemMapper.getProblemForUpdate(request.targetProblemId());
    if (existing != null && existing.getProblemId() != request.targetProblemId()) {
      throw new IllegalStateException("imported provenance is assigned to another problem id");
    }
    if (target != null
        && (existing == null || target.getProblemId() != existing.getProblemId())) {
      throw new IllegalStateException("mapped problem id is already occupied");
    }
    if (existing != null && request.contentSha256().equals(existing.getContentSha256())) {
      return new ProblemImportResult(ProblemImportResult.Action.SKIPPED, existing.getProblemId());
    }

    Problem problem = toProblem(request);
    ProblemImportResult.Action action;
    if (existing == null) {
      problem.setProblemId(request.targetProblemId());
      createImportedProblem(problem);
      createDefaultCategory(problem.getProblemId());
      action = ProblemImportResult.Action.CREATED;
    } else {
      problem.setProblemId(existing.getProblemId());
      problemMapper.updateImportedProblem(problem);
      checkpointMapper.deleteCheckpoint(problem.getProblemId());
      tagMapper.deleteProblemTagRelationship(problem.getProblemId());
      action = ProblemImportResult.Action.UPDATED;
    }
    createTags(problem.getProblemId(), request.tags());
    createCheckpoints(problem.getProblemId(), request.testCases(), request.exactlyMatch());
    problemMapper.bumpCheckpointsVersion(problem.getProblemId());
    return new ProblemImportResult(action, problem.getProblemId());
  }

  void validate(ProblemImportRequest request) {
    if (request == null
        || isBlank(request.sourceSystem())
        || isBlank(request.sourceDomain())
        || isBlank(request.sourceId())
        || request.targetProblemId() == null
        || request.targetProblemId() < 0
        || request.targetProblemId() > 10000
        || request.contentSha256() == null
        || !request.contentSha256().matches("[a-f0-9]{64}")
        || isBlank(request.title())
        || request.timeLimitMs() <= 0
        || request.memoryLimitKb() <= 0
        || isBlank(request.description())
        || isBlank(request.inputFormat())
        || isBlank(request.outputFormat())
        || isBlank(request.sampleInput())
        || isBlank(request.sampleOutput())
        || request.tags() == null
        || request.tags().stream().anyMatch(tag -> isBlank(tag) || tag.length() > 32)
        || request.testCases() == null
        || request.testCases().isEmpty()
        || request.testCases().stream()
            .anyMatch(testCase -> testCase == null || testCase.input() == null || testCase.output() == null)) {
      throw new IllegalArgumentException("invalid problem import request");
    }
  }

  private boolean isBlank(String value) {
    return value == null || value.isBlank();
  }

  private Problem toProblem(ProblemImportRequest request) {
    Problem problem =
        new Problem(
            PublicationStatus.DRAFT,
            request.title(),
            request.timeLimitMs(),
            request.memoryLimitKb(),
            request.description(),
            request.inputFormat(),
            request.outputFormat(),
            request.sampleInput(),
            request.sampleOutput(),
            request.hint());
    problem.setProblemDifficulty(new ProblemDifficulty(1, "primary", "Primary"));
    problem.setSourceSystem(request.sourceSystem());
    problem.setSourceDomain(request.sourceDomain());
    problem.setSourceId(request.sourceId());
    problem.setContentSha256(request.contentSha256());
    return problem;
  }

  private void createImportedProblem(Problem problem) {
    if (problem.getProblemId() != 0) {
      problemMapper.createImportedProblem(problem);
      return;
    }
    String originalMode = problemMapper.getSessionSqlMode();
    String zeroMode =
        originalMode == null || originalMode.isBlank()
            ? "NO_AUTO_VALUE_ON_ZERO"
            : originalMode + ",NO_AUTO_VALUE_ON_ZERO";
    problemMapper.setSessionSqlMode(zeroMode);
    try {
      problemMapper.createImportedProblem(problem);
    } finally {
      problemMapper.setSessionSqlMode(originalMode == null ? "" : originalMode);
    }
  }

  private void createDefaultCategory(long problemId) {
    ProblemCategory category = categoryMapper.getProblemCategoryUsingCategorySlug("uncategorized");
    if (category == null) {
      throw new IllegalStateException("default problem category is missing");
    }
    categoryMapper.createProblemCategoryRelationship(problemId, category);
  }

  private void createTags(long problemId, List<String> tagNames) {
    Set<String> slugs = new HashSet<>();
    for (String tagName : tagNames) {
      String slug = importedTagSlug(tagName);
      if (!slugs.add(slug)) {
        continue;
      }
      ProblemTag tag = tagMapper.getProblemTagUsingTagSlug(slug);
      if (tag == null) {
        tag = new ProblemTag(slug, tagName);
        tagMapper.createImportedProblemTag(tag);
      }
      tagMapper.createProblemTagRelationship(problemId, tag);
    }
  }

  private String importedTagSlug(String tagName) {
    String slug = SlugifyUtils.getSlug(tagName);
    if (slug.length() <= 32) {
      return slug;
    }
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(tagName.getBytes(StandardCharsets.UTF_8));
      return "tag-" + java.util.HexFormat.of().formatHex(digest, 0, 12);
    } catch (NoSuchAlgorithmException error) {
      throw new IllegalStateException("SHA-256 is unavailable", error);
    }
  }

  private void createCheckpoints(
      long problemId, List<ProblemImportTestCase> testCases, boolean exactlyMatch) {
    for (int index = 0; index < testCases.size(); index++) {
      ProblemImportTestCase testCase = testCases.get(index);
      int score = 100 / testCases.size();
      if (index == testCases.size() - 1) {
        score = 100 - score * index;
      }
      checkpointMapper.createCheckpoint(
          new Checkpoint(
              problemId, index, exactlyMatch, score, testCase.input(), testCase.output()));
    }
  }

  private final ProblemMapper problemMapper;
  private final CheckpointMapper checkpointMapper;
  private final ProblemCategoryMapper categoryMapper;
  private final ProblemTagMapper tagMapper;
}
