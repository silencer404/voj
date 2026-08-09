import unittest

from scripts.problem_pipeline.manifest import content_digest

from scripts.problem_pipeline.p00279 import (
    build_p00279_cases,
    build_p00279_problem,
    empty_point_oracle,
    liberty_sets_reference,
    verify_p00279,
)
from scripts.problem_pipeline.planning import build_import_plan
from scripts.problem_pipeline.problem_mapping import ProblemMapping


MAPPING_POLICY = {
    "schemaVersion": 1,
    "sourceIdRange": "P00000-P10000",
    "targetProblemIdStart": 0,
}
MAPPING = ProblemMapping(MAPPING_POLICY, content_digest(MAPPING_POLICY))


class P00279WorkflowTest(unittest.TestCase):
    def test_sample_and_required_edge_cases(self):
        cases = build_p00279_cases(seed=20260809, random_count=100)
        named = {case["name"]: case for case in cases}

        self.assertEqual("8 7", named["sample"]["output"])
        self.assertEqual("2 2", named["opposite-corners"]["output"])
        self.assertEqual("4 2", named["shared-liberty"]["output"])
        self.assertEqual("3 3", named["opponent-blocks-liberty"]["output"])
        self.assertEqual("7 7", named["empty-point-counts-for-both"]["output"])
        self.assertEqual("9 2", named["eye-counts"]["output"])
        self.assertEqual("0 8", named["surrounded-stones"]["output"])
        self.assertEqual("0 0", named["full-board"]["output"])

    def test_independent_solvers_agree_deterministically(self):
        cases = build_p00279_cases(seed=20260809, random_count=300)
        for case in cases:
            self.assertEqual(
                empty_point_oracle(case["instance"]),
                liberty_sets_reference(case["instance"]),
                case["name"],
            )

        report = verify_p00279(seed=20260809, random_count=300)
        self.assertTrue(report["passed"])
        self.assertEqual(310, report["caseCount"])
        self.assertEqual(report, verify_p00279(seed=20260809, random_count=300))

    def test_builds_human_approved_manual_import_plan(self):
        authorization_ref = (
            "user-provided:经 Hydro/hwod_oj 内容所有者书面授权，用于 VOJ 数据迁移测试"
        )
        problem = build_p00279_problem(authorization_ref, seed=20260809, random_count=90)

        self.assertEqual("manual", problem["sourceSystem"])
        self.assertEqual("user-provided", problem["sourceDomain"])
        self.assertEqual("human-approved", problem["workflowState"])
        self.assertTrue(problem["verification"]["passed"])
        self.assertEqual(100, len(problem["testCases"]))

        plan = build_import_plan([problem], ["P00279"], authorization_ref, MAPPING)

        self.assertEqual(1, plan["acceptedCount"])
        self.assertEqual(0, plan["rejectedCount"])
        self.assertEqual("DRAFT", plan["accepted"][0]["status"])
        self.assertTrue(plan["accepted"][0]["exactlyMatch"])


if __name__ == "__main__":
    unittest.main()
