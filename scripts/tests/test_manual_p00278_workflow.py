import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.problem_pipeline.hydro import expand_source_range
from scripts.problem_pipeline.manifest import content_digest
from scripts.problem_pipeline.manual import normalize_manual_problem
from scripts.problem_pipeline.p00278 import (
    bellman_ford_oracle,
    build_p00278_cases,
    dijkstra_reference,
    verify_p00278,
)
from scripts.problem_pipeline.planning import build_import_plan
from scripts.problem_pipeline.problem_mapping import ProblemMapping


MAPPING_POLICY = {
    "schemaVersion": 1,
    "sourceIdRange": "P00000-P10000",
    "targetProblemIdStart": 0,
}
MAPPING = ProblemMapping(MAPPING_POLICY, content_digest(MAPPING_POLICY))


STATEMENT = """一个局域网内有很多台电脑，分别标注为 0 ~ N-1 的数字。相连接的电脑距离不一样，所以感染时间不一样，感染时间用t 表示。其中网络内一台电脑被病毒感染，求其感染网络内所有的电脑最少需要多长时间。如果最后有电脑不会感染，则返回-1.

给定一个数组 times 表示一台电脑把相邻电脑感染所用的时间如图: path[i] = {i,j,t} 表示: 电脑i -> j，电脑i 上的病毒感染j，需要时间 t。

输入描述
第一行输入一个整数N ，表示局域网内电脑个数 N，1<= N<= 200 :第二行输入一个整数M ,表示有 M 条网络连接;
接下来M行 ,每行输入为 i,j,t 。表示电脑i感染电脑 需要时间t。 (1 <=i,j <= N)最后一行为病毒所在的电脑编号
输出描述
输出最少需要多少时间才能感染全部电脑，如果不存在输出 -1

示例1：
输入
4
3
2 1 1
2 3 1
3 4 1
2
输出
2
"""


class ManualP00278WorkflowTest(unittest.TestCase):
    def test_manual_source_does_not_relax_hydro_collection_range(self):
        with self.assertRaises(ValueError):
            expand_source_range("P10001-P10001")

        problem = normalize_manual_problem(
            source_id="P00278",
            title="局域网感染时间",
            statement=STATEMENT,
            authorization_ref="user-provided:chat",
        )

        self.assertEqual("manual", problem["sourceSystem"])
        self.assertEqual("user-provided", problem["sourceDomain"])
        self.assertEqual("P00278", problem["sourceId"])
        self.assertIn("编号范围以输入约束为准，使用 1 到 N", problem["description"])
        self.assertEqual("4\n3\n2 1 1\n2 3 1\n3 4 1\n2", problem["sampleInput"])
        self.assertEqual("2", problem["sampleOutput"])
        self.assertEqual("DRAFT", problem["status"])

    def test_independent_solvers_agree_on_required_edge_cases(self):
        cases = build_p00278_cases(seed=20260804, random_count=200)
        named = {case["name"] for case in cases}

        self.assertTrue(
            {
                "sample",
                "single-node",
                "unreachable",
                "directed-edge",
                "faster-indirect-path",
                "max-node-chain",
                "duplicate-directed-edge",
                "zero-weight-cycle",
            }
            <= named
        )
        for case in cases:
            instance = case["instance"]
            self.assertEqual(
                bellman_ford_oracle(instance),
                dijkstra_reference(instance),
                case["name"],
            )

        report = verify_p00278(seed=20260804, random_count=200)
        self.assertTrue(report["passed"])
        self.assertEqual(208, report["caseCount"])
        self.assertEqual(report, verify_p00278(seed=20260804, random_count=200))

    def test_manual_problem_builds_accepted_dry_run_plan(self):
        problem = normalize_manual_problem(
            "P00278", "局域网感染时间", STATEMENT, "user-provided:chat"
        )
        cases = build_p00278_cases(seed=20260804, random_count=40)
        problem["testCases"] = [
            {"input": case["input"], "output": case["output"]} for case in cases
        ]
        problem["verification"] = verify_p00278(seed=20260804, random_count=200)
        problem["verification"]["reportSha256"] = "a" * 64
        problem["workflowState"] = "human-approved"

        plan = build_import_plan([problem], ["P00278"], "user-provided:chat", MAPPING)

        self.assertEqual("manual", plan["sourceSystem"])
        self.assertEqual(1, plan["acceptedCount"])
        self.assertEqual(0, plan["rejectedCount"])
        self.assertEqual("DRAFT", plan["accepted"][0]["status"])
        self.assertEqual(48, len(plan["accepted"][0]["testCases"]))

    def test_cli_plan_accepts_explicit_manual_source_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            problems = root / "problems"
            problems.mkdir()
            problem = normalize_manual_problem(
                "P00278", "局域网感染时间", STATEMENT, "user-provided:chat"
            )
            cases = build_p00278_cases(seed=7, random_count=4)
            problem["testCases"] = [
                {"input": case["input"], "output": case["output"]} for case in cases
            ]
            problem["verification"] = verify_p00278(seed=7, random_count=4)
            problem["verification"]["reportSha256"] = "b" * 64
            problem["workflowState"] = "human-approved"
            (problems / "P00278.json").write_text(
                json.dumps(problem, ensure_ascii=False), encoding="utf-8"
            )
            output = root / "plan.json"
            mapping = root / "problem_mapping.json"
            mapping.write_text(json.dumps(MAPPING_POLICY), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.problem_pipeline.cli",
                    "plan",
                    "--problems",
                    str(problems),
                    "--source-id",
                    "P00278",
                    "--authorization-ref",
                    "user-provided:chat",
                    "--mapping",
                    str(mapping),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("manual", json.loads(output.read_text())["sourceSystem"])


if __name__ == "__main__":
    unittest.main()
