from typing import Any

from .manifest import content_digest
from .problem_mapping import ProblemMapping
from .verification import CompatibilityError, require_supported_judge


def _rejection_codes(problem: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    if problem.get("workflowState") != "human-approved":
        codes.append("not-approved")
    verification = problem.get("verification")
    if not isinstance(verification, dict) or verification.get("passed") is not True:
        codes.append("verification-failed")
    tests = problem.get("testCases")
    if not isinstance(tests, list) or not tests:
        codes.append("missing-tests")
    elif any(
        not isinstance(test, dict)
        or not isinstance(test.get("input"), str)
        or not isinstance(test.get("output"), str)
        for test in tests
    ):
        codes.append("invalid-tests")
    try:
        require_supported_judge(str(problem.get("judgeMode") or ""))
    except CompatibilityError:
        codes.append("unsupported-judge")
    return codes


def _persisted_content(problem: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "sourceSystem",
        "sourceDomain",
        "sourceId",
        "title",
        "timeLimitMs",
        "memoryLimitKb",
        "description",
        "inputFormat",
        "outputFormat",
        "sampleInput",
        "sampleOutput",
        "hint",
        "judgeMode",
        "tags",
        "testCases",
    )
    return {field: problem.get(field) for field in fields}


def build_import_plan(
    problems: list[dict[str, Any]],
    expected_source_ids: list[str],
    authorization_ref: str,
    mapping: ProblemMapping,
) -> dict[str, Any]:
    if not authorization_ref.strip():
        raise ValueError("authorization reference is required")
    by_source_id: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    source_systems: set[str] = set()
    for problem in problems:
        source_id = str(problem.get("sourceId") or "")
        source_system = str(problem.get("sourceSystem") or "")
        if source_system:
            source_systems.add(source_system)
        if source_id in by_source_id:
            duplicates.add(source_id)
        by_source_id[source_id] = problem

    if len(source_systems) != 1:
        raise ValueError("an import plan must contain exactly one source system")
    source_system = next(iter(source_systems))

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source_id in expected_source_ids:
        problem = by_source_id.get(source_id)
        if problem is None:
            rejected.append({"sourceId": source_id, "codes": ["missing-source"]})
            continue
        codes = _rejection_codes(problem)
        if source_id in duplicates:
            codes.append("duplicate-source")
        if problem.get("authorizationRef") != authorization_ref:
            codes.append("authorization-mismatch")
        if codes:
            rejected.append({"sourceId": source_id, "codes": sorted(set(codes))})
            continue
        importable = dict(problem)
        importable["status"] = "DRAFT"
        importable["exactlyMatch"] = True
        importable["targetProblemId"] = mapping.target_problem_id(source_id)
        importable["contentSha256"] = content_digest(_persisted_content(problem))
        accepted.append(importable)

    plan: dict[str, Any] = {
        "schemaVersion": 2,
        "sourceSystem": source_system,
        "authorizationRef": authorization_ref,
        "mappingSha256": mapping.sha256,
        "expectedCount": len(expected_source_ids),
        "acceptedCount": len(accepted),
        "rejectedCount": len(rejected),
        "accepted": accepted,
        "rejected": rejected,
    }
    plan["planSha256"] = content_digest(plan)
    return plan
