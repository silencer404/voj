import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.problem_pipeline.public_content import (
    build_public_content,
    load_public_content,
    write_public_content,
)
from scripts.problem_pipeline.segmentation import (
    SegmentationError,
    validate_segmentation,
)


LINES = [
    "## 题目描述",
    "给定两个整数。",
    "## 输入格式",
    "输入两个整数。",
    "## 输出格式",
    "输出它们的和。",
    "## 样例 1",
    "输入",
    "1 2",
    "输出",
    "3",
    "## 样例 2",
    "输入",
    "4 5",
    "输出",
    "9",
]
SEGMENTS = [
    {"kind": "structure", "startLine": 1, "endLine": 1, "sampleIndex": None},
    {"kind": "description", "startLine": 2, "endLine": 2, "sampleIndex": None},
    {"kind": "structure", "startLine": 3, "endLine": 3, "sampleIndex": None},
    {"kind": "inputFormat", "startLine": 4, "endLine": 4, "sampleIndex": None},
    {"kind": "structure", "startLine": 5, "endLine": 5, "sampleIndex": None},
    {"kind": "outputFormat", "startLine": 6, "endLine": 6, "sampleIndex": None},
    {"kind": "structure", "startLine": 7, "endLine": 8, "sampleIndex": None},
    {"kind": "sampleInput", "startLine": 9, "endLine": 9, "sampleIndex": 1},
    {"kind": "structure", "startLine": 10, "endLine": 10, "sampleIndex": None},
    {"kind": "sampleOutput", "startLine": 11, "endLine": 11, "sampleIndex": 1},
    {"kind": "structure", "startLine": 12, "endLine": 13, "sampleIndex": None},
    {"kind": "sampleInput", "startLine": 14, "endLine": 14, "sampleIndex": 2},
    {"kind": "structure", "startLine": 15, "endLine": 15, "sampleIndex": None},
    {"kind": "sampleOutput", "startLine": 16, "endLine": 16, "sampleIndex": 2},
]


class SemanticSegmentationTest(unittest.TestCase):
    def public_content(self):
        return build_public_content(
            source_system="manual",
            source_domain="user-provided",
            source_id="P00605",
            source_url="",
            authorization_ref="user-provided:test",
            title="求和",
            statement="\n".join(LINES),
            time_limit_ms=1000,
            memory_limit_kb=262144,
            judge_mode="default",
            tags=[],
        )

    def test_validates_ranges_and_merges_all_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_path = root / "public-content.json"
            result_path = root / "segmentation.json"
            public = self.public_content()
            write_public_content(public_path, public)
            result_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "publicContentSha256": public["publicContentSha256"],
                        "segments": SEGMENTS,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            problem, validation = validate_segmentation(public_path, result_path)

            self.assertEqual("给定两个整数。", problem["description"])
            self.assertEqual("样例 1\n1 2\n\n样例 2\n4 5", problem["sampleInput"])
            self.assertEqual("样例 1\n3\n\n样例 2\n9", problem["sampleOutput"])
            self.assertEqual(2, validation["sampleCount"])

    def test_rejects_duplicate_keys_and_incomplete_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_path = root / "public-content.json"
            public = self.public_content()
            write_public_content(public_path, public)
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"schemaVersion":1,"schemaVersion":1,"publicContentSha256":"x","segments":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SegmentationError, "duplicate JSON key"):
                validate_segmentation(public_path, duplicate)

            incomplete = root / "incomplete.json"
            incomplete.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "publicContentSha256": public["publicContentSha256"],
                        "segments": SEGMENTS[:-1],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SegmentationError, "complete public content"):
                validate_segmentation(public_path, incomplete)

            out_of_order = root / "out-of-order.json"
            reordered = [dict(segment) for segment in SEGMENTS]
            reordered[7]["sampleIndex"] = 2
            reordered[9]["sampleIndex"] = 2
            reordered[11]["sampleIndex"] = 1
            reordered[13]["sampleIndex"] = 1
            out_of_order.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "publicContentSha256": public["publicContentSha256"],
                        "segments": reordered,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SegmentationError, "out of order"):
                validate_segmentation(public_path, out_of_order)

    def test_prepare_manual_cli_uses_shared_public_content_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            title = root / "title.txt"
            statement = root / "statement.txt"
            title.write_text("求和\n", encoding="utf-8")
            statement.write_text("\r\n".join(LINES), encoding="utf-8")
            workspace = root / "workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.problem_pipeline.cli",
                    "prepare-manual",
                    "--workspace",
                    str(workspace),
                    "--source-id",
                    "P00605",
                    "--authorization-ref",
                    "user-provided:test",
                    "--title-file",
                    str(title),
                    "--statement-file",
                    str(statement),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            public = load_public_content(
                workspace / "problems" / "P00605" / "public-content.json"
            )
            self.assertEqual(LINES, public["contentLines"])
            self.assertEqual("manual", public["sourceSystem"])

    def test_validate_cli_writes_problem_and_validation_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            problem_directory = workspace / "problems" / "P00605"
            public = self.public_content()
            write_public_content(problem_directory / "public-content.json", public)
            (problem_directory / "segmentation.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "publicContentSha256": public["publicContentSha256"],
                        "segments": SEGMENTS,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.problem_pipeline.cli",
                    "validate",
                    "--workspace",
                    str(workspace),
                    "--source-id",
                    "P00605",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["passed"])
            problem = json.loads(
                (problem_directory / "problem.json").read_text(encoding="utf-8")
            )
            self.assertEqual("求和", problem["title"])
            self.assertEqual("parsed", problem["workflowState"])
            self.assertTrue(
                (problem_directory / "segmentation-validation.json").is_file()
            )

    def test_prepare_manual_rejects_unscoped_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            title = root / "title.txt"
            statement = root / "statement.txt"
            title.write_text("求和", encoding="utf-8")
            statement.write_text("内容", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.problem_pipeline.cli",
                    "prepare-manual",
                    "--workspace",
                    str(root / "workspace"),
                    "--source-id",
                    "P00605",
                    "--authorization-ref",
                    "invalid",
                    "--title-file",
                    str(title),
                    "--statement-file",
                    str(statement),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
