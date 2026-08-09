package org.verwandlung.voj.web.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;

import org.verwandlung.voj.web.mapper.CheckpointMapper;
import org.verwandlung.voj.web.mapper.ProblemCategoryMapper;
import org.verwandlung.voj.web.mapper.ProblemMapper;
import org.verwandlung.voj.web.mapper.ProblemTagMapper;
import org.verwandlung.voj.web.model.Checkpoint;
import org.verwandlung.voj.web.model.Problem;
import org.verwandlung.voj.web.model.ProblemCategory;
import org.verwandlung.voj.web.model.ProblemImportRequest;
import org.verwandlung.voj.web.model.ProblemImportResult;
import org.verwandlung.voj.web.model.ProblemImportTestCase;
import org.verwandlung.voj.web.model.ProblemTag;
import org.verwandlung.voj.web.model.PublicationStatus;

class ProblemImportServiceTest {
  @Test
  void createsDraftProblemAndVersionedCheckpointsForNewSource() {
    ProblemMapper problemMapper = mock(ProblemMapper.class);
    CheckpointMapper checkpointMapper = mock(CheckpointMapper.class);
    ProblemCategoryMapper categoryMapper = mock(ProblemCategoryMapper.class);
    ProblemTagMapper tagMapper = mock(ProblemTagMapper.class);
    ProblemCategory uncategorized = new ProblemCategory(1, "uncategorized", "Uncategorized", 0);
    when(categoryMapper.getProblemCategoryUsingCategorySlug("uncategorized"))
        .thenReturn(uncategorized);
    when(tagMapper.getProblemTagUsingTagSlug(any()))
        .thenAnswer(
            invocation -> new ProblemTag(10, invocation.getArgument(0), invocation.getArgument(0)));
    when(problemMapper.getProblemUsingProvenanceForUpdate("hydro", "hwod_oj", "P00456"))
        .thenReturn(null);
    when(problemMapper.createImportedProblem(any(Problem.class))).thenReturn(1);
    ProblemImportService service =
        new ProblemImportService(problemMapper, checkpointMapper, categoryMapper, tagMapper);

    ProblemImportResult result = service.importProblem(request("a".repeat(64)));

    assertEquals(ProblemImportResult.Action.CREATED, result.action());
    assertEquals(456, result.problemId());
    ArgumentCaptor<Problem> problemCaptor = ArgumentCaptor.forClass(Problem.class);
    verify(problemMapper).createImportedProblem(problemCaptor.capture());
    Problem created = problemCaptor.getValue();
    assertEquals(456, created.getProblemId());
    assertEquals(PublicationStatus.DRAFT, created.getStatus());
    assertEquals("hydro", created.getSourceSystem());
    assertEquals("hwod_oj", created.getSourceDomain());
    assertEquals("P00456", created.getSourceId());
    assertEquals("a".repeat(64), created.getContentSha256());

    ArgumentCaptor<Checkpoint> checkpointCaptor = ArgumentCaptor.forClass(Checkpoint.class);
    verify(checkpointMapper, org.mockito.Mockito.times(2))
        .createCheckpoint(checkpointCaptor.capture());
    List<Checkpoint> checkpoints = checkpointCaptor.getAllValues();
    assertEquals(List.of(0, 1), checkpoints.stream().map(Checkpoint::getCheckpointId).toList());
    assertEquals(List.of(50, 50), checkpoints.stream().map(Checkpoint::getScore).toList());
    assertFalse(checkpoints.get(0).isExactlyMatch());
    verify(categoryMapper).createProblemCategoryRelationship(456, uncategorized);
    verify(tagMapper, org.mockito.Mockito.times(2))
        .createProblemTagRelationship(org.mockito.ArgumentMatchers.eq(456L), any(ProblemTag.class));
    ArgumentCaptor<String> slugCaptor = ArgumentCaptor.forClass(String.class);
    verify(tagMapper, org.mockito.Mockito.times(2)).getProblemTagUsingTagSlug(slugCaptor.capture());
    org.junit.jupiter.api.Assertions.assertTrue(
        slugCaptor.getAllValues().stream().allMatch(slug -> slug.length() <= 32));
    assertEquals(2, new java.util.HashSet<>(slugCaptor.getAllValues()).size());
    InOrder order = inOrder(problemMapper, checkpointMapper);
    order.verify(problemMapper).createImportedProblem(any(Problem.class));
    order.verify(checkpointMapper, org.mockito.Mockito.times(2))
        .createCheckpoint(any(Checkpoint.class));
    order.verify(problemMapper).bumpCheckpointsVersion(456);
  }

  @Test
  void skipsExactReimportWithoutChangingProblemOrCheckpoints() {
    ProblemMapper problemMapper = mock(ProblemMapper.class);
    CheckpointMapper checkpointMapper = mock(CheckpointMapper.class);
    ProblemCategoryMapper categoryMapper = mock(ProblemCategoryMapper.class);
    ProblemTagMapper tagMapper = mock(ProblemTagMapper.class);
    Problem existing = importedProblem(456, "a".repeat(64));
    when(problemMapper.getProblemUsingProvenanceForUpdate("hydro", "hwod_oj", "P00456"))
        .thenReturn(existing);
    ProblemImportService service =
        new ProblemImportService(problemMapper, checkpointMapper, categoryMapper, tagMapper);

    ProblemImportResult result = service.importProblem(request("a".repeat(64)));

    assertEquals(ProblemImportResult.Action.SKIPPED, result.action());
    assertEquals(456, result.problemId());
    verify(problemMapper, never()).updateImportedProblem(any(Problem.class));
    verify(problemMapper, never()).bumpCheckpointsVersion(456);
    verifyNoInteractions(checkpointMapper, categoryMapper, tagMapper);
  }

  @Test
  void updatesExistingProblemAndReplacesCheckpointsWhenDigestChanges() {
    ProblemMapper problemMapper = mock(ProblemMapper.class);
    CheckpointMapper checkpointMapper = mock(CheckpointMapper.class);
    ProblemCategoryMapper categoryMapper = mock(ProblemCategoryMapper.class);
    ProblemTagMapper tagMapper = mock(ProblemTagMapper.class);
    Problem existing = importedProblem(456, "a".repeat(64));
    when(problemMapper.getProblemUsingProvenanceForUpdate("hydro", "hwod_oj", "P00456"))
        .thenReturn(existing);
    ProblemImportService service =
        new ProblemImportService(problemMapper, checkpointMapper, categoryMapper, tagMapper);

    ProblemImportResult result = service.importProblem(request("b".repeat(64)));

    assertEquals(ProblemImportResult.Action.UPDATED, result.action());
    assertEquals(456, result.problemId());
    ArgumentCaptor<Problem> problemCaptor = ArgumentCaptor.forClass(Problem.class);
    verify(problemMapper).updateImportedProblem(problemCaptor.capture());
    assertEquals(456, problemCaptor.getValue().getProblemId());
    assertEquals(PublicationStatus.DRAFT, problemCaptor.getValue().getStatus());
    assertEquals("b".repeat(64), problemCaptor.getValue().getContentSha256());
    InOrder order = inOrder(problemMapper, checkpointMapper);
    order.verify(problemMapper).updateImportedProblem(any(Problem.class));
    order.verify(checkpointMapper).deleteCheckpoint(456);
    order.verify(checkpointMapper, org.mockito.Mockito.times(2))
        .createCheckpoint(any(Checkpoint.class));
    order.verify(problemMapper).bumpCheckpointsVersion(456);
    verify(tagMapper).deleteProblemTagRelationship(456);
    verify(tagMapper, org.mockito.Mockito.times(2))
        .createProblemTagRelationship(org.mockito.ArgumentMatchers.eq(456L), any(ProblemTag.class));
  }

  @Test
  void rejectsMappedTargetOccupiedByAnotherProblem() {
    ProblemMapper problemMapper = mock(ProblemMapper.class);
    CheckpointMapper checkpointMapper = mock(CheckpointMapper.class);
    ProblemCategoryMapper categoryMapper = mock(ProblemCategoryMapper.class);
    ProblemTagMapper tagMapper = mock(ProblemTagMapper.class);
    Problem occupant = importedProblem(456, "a".repeat(64));
    occupant.setSourceId("P00999");
    when(problemMapper.getProblemUsingProvenanceForUpdate("hydro", "hwod_oj", "P00456"))
        .thenReturn(null);
    when(problemMapper.getProblemForUpdate(456)).thenReturn(occupant);
    ProblemImportService service =
        new ProblemImportService(problemMapper, checkpointMapper, categoryMapper, tagMapper);

    assertThrows(IllegalStateException.class, () -> service.importProblem(request("a".repeat(64))));

    verify(problemMapper, never()).createImportedProblem(any(Problem.class));
    verifyNoInteractions(checkpointMapper, categoryMapper, tagMapper);
  }

  @Test
  void rejectsInvalidDigestAndEmptyTestsBeforePersistence() {
    ProblemMapper problemMapper = mock(ProblemMapper.class);
    CheckpointMapper checkpointMapper = mock(CheckpointMapper.class);
    ProblemCategoryMapper categoryMapper = mock(ProblemCategoryMapper.class);
    ProblemTagMapper tagMapper = mock(ProblemTagMapper.class);
    ProblemImportService service =
        new ProblemImportService(problemMapper, checkpointMapper, categoryMapper, tagMapper);

    assertThrows(IllegalArgumentException.class, () -> service.importProblem(request("bad")));
    ProblemImportRequest emptyTests =
        new ProblemImportRequest(
            "hydro",
            "hwod_oj",
            "P00456",
            456L,
            "a".repeat(64),
            "采购订单",
            1000,
            262144,
            "题目描述",
            "输入格式",
            "输出格式",
            "2",
            "3",
            "",
            false,
            List.of("数据结构", "模拟"),
            List.of());
    ProblemImportRequest nullTestCase =
        new ProblemImportRequest(
            "hydro",
            "hwod_oj",
            "P00456",
            456L,
            "a".repeat(64),
            "采购订单",
            1000,
            262144,
            "题目描述",
            "输入格式",
            "输出格式",
            "2",
            "3",
            "",
            true,
            List.of("数据结构", "模拟"),
            List.of(new ProblemImportTestCase(null, "3")));
    assertThrows(IllegalArgumentException.class, () -> service.importProblem(nullTestCase));
    ProblemImportRequest invalidContent =
        new ProblemImportRequest(
            "hydro",
            "hwod_oj",
            "P00456",
            456L,
            "a".repeat(64),
            "",
            0,
            -1,
            "",
            "",
            "",
            "",
            "",
            "",
            true,
            List.of("数据结构", "模拟"),
            List.of(new ProblemImportTestCase("1", "2")));
    assertThrows(IllegalArgumentException.class, () -> service.importProblem(invalidContent));
    verifyNoInteractions(problemMapper, checkpointMapper);
  }

  private Problem importedProblem(long problemId, String digest) {
    Problem problem = new Problem();
    problem.setProblemId(problemId);
    problem.setSourceSystem("hydro");
    problem.setSourceDomain("hwod_oj");
    problem.setSourceId("P00456");
    problem.setContentSha256(digest);
    return problem;
  }

  private ProblemImportRequest request(String digest) {
    return new ProblemImportRequest(
        "hydro",
        "hwod_oj",
        "P00456",
        456L,
        digest,
        "采购订单",
        1000,
        262144,
        "题目描述",
        "输入格式",
        "输出格式",
        "2",
        "3",
        "",
        false,
        List.of("数组", "模拟"),
        List.of(
            new ProblemImportTestCase("1", "2"),
            new ProblemImportTestCase("2", "3")));
  }
}
