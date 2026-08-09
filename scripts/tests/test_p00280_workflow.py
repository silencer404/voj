import unittest

from scripts.problem_pipeline.manifest import content_digest

from scripts.problem_pipeline.p00280 import (
    build_p00280_cases,
    build_p00280_problem,
    pattern_matches_oracle,
    pattern_matches_reference,
    verify_p00280,
)
from scripts.problem_pipeline.planning import build_import_plan
from scripts.problem_pipeline.problem_mapping import ProblemMapping


MAPPING_POLICY = {
    "schemaVersion": 1,
    "sourceIdRange": "P00000-P10000",
    "targetProblemIdStart": 0,
}
MAPPING = ProblemMapping(MAPPING_POLICY, content_digest(MAPPING_POLICY))


class P00280WorkflowTest(unittest.TestCase):
    def test_samples_and_required_edge_cases(self):
        cases = build_p00280_cases(seed=20260809, random_count=100)
        named = {case["name"]: case for case in cases}

        self.assertEqual("1234567*", named["sample-star-suffix"]["output"])
        self.assertEqual("null", named["sample-question-index-restriction"]["output"])
        self.assertEqual("123456789012345", named["exact-match"]["output"])
        self.assertEqual("*123456789012345,123456789012345*", named["star-empty"]["output"])
        self.assertEqual("*,*5", named["star-whole-imsi"]["output"])
        self.assertEqual("123*345", named["star-middle"]["output"])
        self.assertEqual("1?3456789012345", named["question-at-odd-index"]["output"])
        self.assertEqual("123*?345", named["question-after-star"]["output"])
        self.assertEqual("null", named["pattern-too-long"]["output"])
        self.assertEqual("null", named["no-match"]["output"])

    def test_independent_solvers_agree_deterministically(self):
        cases = build_p00280_cases(seed=20260809, random_count=300)
        for case in cases:
            instance = case["instance"]
            for pattern in instance["patterns"]:
                self.assertEqual(
                    pattern_matches_oracle(pattern, instance["imsi"]),
                    pattern_matches_reference(pattern, instance["imsi"]),
                    case["name"],
                )

        report = verify_p00280(seed=20260809, random_count=300)
        self.assertTrue(report["passed"])
        self.assertEqual(312, report["caseCount"])
        self.assertEqual(report, verify_p00280(seed=20260809, random_count=300))

    def test_builds_human_approved_manual_import_plan(self):
        authorization_ref = "user-provided:工单号2026080900280"
        problem = build_p00280_problem(authorization_ref, seed=20260809, random_count=88)

        self.assertEqual("manual", problem["sourceSystem"])
        self.assertEqual("user-provided", problem["sourceDomain"])
        self.assertEqual("human-approved", problem["workflowState"])
        self.assertTrue(problem["verification"]["passed"])
        self.assertEqual(100, len(problem["testCases"]))

        plan = build_import_plan([problem], ["P00280"], authorization_ref, MAPPING)

        self.assertEqual(1, plan["acceptedCount"])
        self.assertEqual(0, plan["rejectedCount"])
        self.assertEqual("DRAFT", plan["accepted"][0]["status"])
        self.assertTrue(plan["accepted"][0]["exactlyMatch"])


if __name__ == "__main__":
    unittest.main()
