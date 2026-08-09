import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.problem_pipeline.browser import (
    BrowserFetchError,
    build_browser_command,
    fetch_problem_page,
)
from scripts.problem_pipeline.collector import (
    CollectionHalted,
    collect_authorized_pages,
    validate_browser_environment,
)
from scripts.problem_pipeline.hydro import (
    CollectionState,
    HydroParseError,
    expand_source_range,
    parse_problem_html,
)
from scripts.problem_pipeline.manifest import build_manifest, content_digest
from scripts.problem_pipeline.planning import build_import_plan
from scripts.problem_pipeline.problem_mapping import ProblemMapping
from scripts.problem_pipeline.verification import (
    CompatibilityError,
    differential_verify,
    require_supported_judge,
)


SYNTHETIC_CONTENT = """## 题目描述
给定订单。

## 输入格式
第一行是 n。

## 输出格式
输出答案。

```input1
2
```

```output1
3
```"""
SYNTHETIC_LEGACY_CONTENT = """```markdown
虚构题目说明。

输入描述
虚构输入约束。
输出描述
虚构输出要求。

样例 1
输入：
alpha
输出：
beta

样例 2
输入：
gamma
输出：
delta
```"""
SYNTHETIC_PLAIN_LEGACY_CONTENT = """虚构题目说明。
输入描述
输入:
虚构输入约束。
输出描述
虚构输出要求。
输入：
alpha
输出：
beta"""
SYNTHETIC_PLAIN_FORMAT_CONTENT = """虚构题目说明。
输入格式
虚构输入约束。
输出格式
虚构输出要求。
示例1
输入：
alpha
输出：
beta"""
SYNTHETIC_PLAIN_DESCRIPTION_SAMPLE_CONTENT = """虚构题目说明。
输入描述
虚构输入约束。
输出描述
虚构输出要求。
示例1
输入
alpha
输出
beta"""
SYNTHETIC_PLAIN_DESCRIPTION_MIXED_SAMPLE_CONTENT = """虚构题目说明。
输入描述
虚构输入约束。
输出描述
虚构输出要求。
示例1
输入:
alpha
输出
beta"""
SYNTHETIC_MULTIPLE_PLAIN_DESCRIPTION_SAMPLES_CONTENT = """虚构题目说明。
输入描述
虚构输入约束。
输出描述
虚构输出要求。
示例1
输入
alpha
输出
beta
说明
第一组虚构说明。
示例2
输入
gamma
输出
delta
说明
第二组虚构说明。"""
SYNTHETIC_COLON_DESCRIPTION_SAMPLE_CONTENT = """虚构题目说明。
输入描述：
虚构输入约束。
输出描述：
虚构输出要求。
示例1
输入
alpha
输出：
beta
说明：
虚构说明。"""
SYNTHETIC_MIXED_COLON_MULTIPLE_SAMPLES_CONTENT = """虚构题目说明。
输入描述
虚构输入约束。
输出描述
虚构输出要求。
示例1
输入:
alpha
输出：
beta
说明：
第一组虚构说明。
示例2
输入：
gamma
输出：
delta"""
SYNTHETIC_CONTEXT = {
    "pdoc": {
        "pid": "P00456",
        "title": "采购订单",
        "content": json.dumps({"zh": SYNTHETIC_CONTENT}, ensure_ascii=False),
        "config": {"time": "1s", "memory": "256m", "type": "default"},
        "tag": ["数组", "模拟"],
        "data": [{"name": "private.in"}],
    }
}
SYNTHETIC_HTML = (
    "<!doctype html><html><head><title>Synthetic</title>"
    "<script>alert('ignored')</script></head><body><script>"
    "window.UiContextNew = "
    + json.dumps(SYNTHETIC_CONTEXT, ensure_ascii=False)
    + ";</script></body></html>"
)
MAPPING_POLICY = {
    "schemaVersion": 1,
    "sourceIdRange": "P00000-P10000",
    "targetProblemIdStart": 0,
}
MAPPING = ProblemMapping(MAPPING_POLICY, content_digest(MAPPING_POLICY))


class HydroPipelineTest(unittest.TestCase):
    def test_expands_inclusive_fixed_width_range(self):
        ids = expand_source_range("P00000-P10000")

        self.assertEqual(10001, len(ids))
        self.assertEqual("P00000", ids[0])
        self.assertEqual("P10000", ids[-1])
        self.assertEqual(["P00279"], expand_source_range("P00279-P00279"))

    def test_rejects_out_of_scope_reversed_or_malformed_range(self):
        invalid_ranges = (
            "P10001-P10001",
            "P10000-P00000",
            "P0000-P00000",
            "P000000-P00000",
            "Q00000-P00000",
        )
        for source_range in invalid_ranges:
            with self.subTest(source_range=source_range):
                with self.assertRaises(ValueError):
                    expand_source_range(source_range)

    def test_parses_only_public_problem_fields(self):
        problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")

        self.assertEqual("P00456", problem["sourceId"])
        self.assertEqual("采购订单", problem["title"])
        self.assertEqual(1000, problem["timeLimitMs"])
        self.assertEqual(262144, problem["memoryLimitKb"])
        self.assertEqual("2", problem["sampleInput"])
        self.assertEqual("3", problem["sampleOutput"])
        self.assertEqual(["数组", "模拟"], problem["tags"])
        self.assertEqual("DRAFT", problem["status"])
        serialized = json.dumps(problem, ensure_ascii=False)
        self.assertNotIn("private.in", serialized)
        self.assertNotIn("<script", serialized.lower())

    def test_parses_strict_legacy_markdown_fence_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_LEGACY_CONTENT}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("虚构题目说明。", problem["description"])
        self.assertEqual("虚构输入约束。", problem["inputFormat"])
        self.assertEqual("虚构输出要求。", problem["outputFormat"])
        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        serialized = json.dumps(problem, ensure_ascii=False)
        self.assertNotIn("private.in", serialized)
        self.assertNotIn("```markdown", serialized)

    def test_rejects_incomplete_legacy_markdown_fence_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_LEGACY_CONTENT.replace("输出：", "结果：", 1)
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError, "legacy marker is missing or duplicated: 输出："
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_strict_plain_legacy_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_PLAIN_LEGACY_CONTENT}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("虚构题目说明。", problem["description"])
        self.assertEqual("输入:\n虚构输入约束。", problem["inputFormat"])
        self.assertEqual("虚构输出要求。", problem["outputFormat"])
        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        serialized = json.dumps(problem, ensure_ascii=False)
        self.assertNotIn("private.in", serialized)
        self.assertNotIn("<script", serialized.lower())

    def test_rejects_incomplete_plain_legacy_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_PLAIN_LEGACY_CONTENT.replace("输出：", "结果：", 1)
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError, "plain legacy marker is missing or duplicated: 输出："
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_strict_plain_format_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_PLAIN_FORMAT_CONTENT}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("虚构题目说明。", problem["description"])
        self.assertEqual("虚构输入约束。", problem["inputFormat"])
        self.assertEqual("虚构输出要求。", problem["outputFormat"])
        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        self.assertNotIn("private.in", json.dumps(problem, ensure_ascii=False))

    def test_rejects_incomplete_plain_format_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_PLAIN_FORMAT_CONTENT.replace("示例1", "示例 1", 1)
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError, "plain format marker is missing or duplicated: 示例1"
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_strict_plain_description_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_PLAIN_DESCRIPTION_SAMPLE_CONTENT}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("虚构题目说明。", problem["description"])
        self.assertEqual("虚构输入约束。", problem["inputFormat"])
        self.assertEqual("虚构输出要求。", problem["outputFormat"])
        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        self.assertNotIn("private.in", json.dumps(problem, ensure_ascii=False))

    def test_rejects_incomplete_plain_description_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_PLAIN_DESCRIPTION_SAMPLE_CONTENT.replace(
            "\n输出\n", "\n结果\n", 1
        )
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError,
            "plain description sample marker is missing or duplicated: 输出",
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_strict_plain_description_mixed_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_PLAIN_DESCRIPTION_MIXED_SAMPLE_CONTENT},
            ensure_ascii=False,
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("虚构题目说明。", problem["description"])
        self.assertEqual("虚构输入约束。", problem["inputFormat"])
        self.assertEqual("虚构输出要求。", problem["outputFormat"])
        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])

    def test_rejects_incomplete_plain_description_mixed_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_PLAIN_DESCRIPTION_MIXED_SAMPLE_CONTENT.replace(
            "\n输出\n", "\n结果\n", 1
        )
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError,
            "plain description sample marker is missing or duplicated: 输出",
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_only_first_plain_description_sample(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_MULTIPLE_PLAIN_DESCRIPTION_SAMPLES_CONTENT},
            ensure_ascii=False,
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        serialized = json.dumps(problem, ensure_ascii=False)
        self.assertNotIn("gamma", serialized)
        self.assertNotIn("delta", serialized)
        self.assertNotIn("第一组虚构说明", serialized)

    def test_rejects_duplicate_markers_within_first_plain_sample(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_MULTIPLE_PLAIN_DESCRIPTION_SAMPLES_CONTENT.replace(
            "alpha\n输出", "alpha\n输入\nextra\n输出", 1
        )
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError,
            "plain description sample marker is missing or duplicated: 输入",
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_strict_colon_description_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_COLON_DESCRIPTION_SAMPLE_CONTENT}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("虚构题目说明。", problem["description"])
        self.assertEqual("虚构输入约束。", problem["inputFormat"])
        self.assertEqual("虚构输出要求。", problem["outputFormat"])
        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        self.assertNotIn("虚构说明", json.dumps(problem, ensure_ascii=False))

    def test_rejects_incomplete_colon_description_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_COLON_DESCRIPTION_SAMPLE_CONTENT.replace(
            "输入描述：", "入参描述：", 1
        )
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError,
            "unsupported plain description label combination",
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_strict_mixed_colon_multiple_sample_structure(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["content"] = json.dumps(
            {"zh": SYNTHETIC_MIXED_COLON_MULTIPLE_SAMPLES_CONTENT},
            ensure_ascii=False,
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("alpha", problem["sampleInput"])
        self.assertEqual("beta", problem["sampleOutput"])
        serialized = json.dumps(problem, ensure_ascii=False)
        self.assertNotIn("gamma", serialized)
        self.assertNotIn("delta", serialized)
        self.assertNotIn("第一组虚构说明", serialized)

    def test_rejects_unknown_mixed_colon_sample_combination(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        malformed = SYNTHETIC_MIXED_COLON_MULTIPLE_SAMPLES_CONTENT.replace(
            "输入:", "输入：", 1
        )
        context["pdoc"]["content"] = json.dumps(
            {"zh": malformed}, ensure_ascii=False
        )
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        with self.assertRaisesRegex(
            HydroParseError, "unsupported plain description label combination"
        ):
            parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_legacy_resource_limit_range(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["config"] = {
            "timeMin": 500,
            "timeMax": 1000,
            "memoryMin": 128,
            "memoryMax": 256,
            "type": "default",
        }
        html = (
            "<script>window.UiContextNew = "
            + json.dumps(context, ensure_ascii=False)
            + ";</script>"
        )

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual(1000, problem["timeLimitMs"])
        self.assertEqual(262144, problem["memoryLimitKb"])

    def test_rejects_malformed_legacy_resource_limit_range(self):
        for config in (
            {"timeMin": 1000, "timeMax": 500, "memoryMin": 128, "memoryMax": 256},
            {"timeMin": 500, "timeMax": 1000, "memoryMin": 256},
            {"timeMin": 500, "timeMax": 1000, "memoryMin": 0, "memoryMax": 256},
        ):
            with self.subTest(config=config):
                context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
                context["pdoc"]["config"] = config
                html = (
                    "<script>window.UiContextNew = "
                    + json.dumps(context, ensure_ascii=False)
                    + ";</script>"
                )
                with self.assertRaises(HydroParseError):
                    parse_problem_html(html, "P00456", "authorization-42")

    def test_parses_single_quoted_json_context(self):
        context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
        context["pdoc"]["title"] = "采购方's订单"
        encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        javascript_string = encoded.replace("\\", "\\\\").replace("'", "\\'")
        html = f"<script>window.UiContextNew = '{javascript_string}';</script>"

        problem = parse_problem_html(html, "P00456", "authorization-42")

        self.assertEqual("采购方's订单", problem["title"])
        self.assertEqual("2", problem["sampleInput"])

    def test_rejects_malformed_single_quoted_json_context(self):
        malformed = "<script>window.UiContextNew = '{\\'pdoc\\':{}}';</script>"

        with self.assertRaises(HydroParseError):
            parse_problem_html(malformed, "P00456", "authorization-42")

    def test_rejects_page_identity_mismatch_and_missing_context(self):
        with self.assertRaises(HydroParseError):
            parse_problem_html(SYNTHETIC_HTML, "P00457", "authorization-42")
        with self.assertRaises(HydroParseError):
            parse_problem_html("<html></html>", "P00456", "authorization-42")

    def test_digest_and_manifest_are_deterministic(self):
        problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")
        reordered = dict(reversed(list(problem.items())))

        self.assertEqual(content_digest(problem), content_digest(reordered))
        first = build_manifest([problem], "authorization-42")
        second = build_manifest([reordered], "authorization-42")
        self.assertEqual(first, second)

    def test_collection_preserves_unstructured_public_content_for_segmentation(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            unstructured_content = SYNTHETIC_CONTENT.replace(
                "## 题目描述", "未标记的公开题干"
            )
            context = json.loads(json.dumps(SYNTHETIC_CONTEXT))
            context["pdoc"]["content"] = json.dumps(
                {"zh": unstructured_content}, ensure_ascii=False
            )
            html = (
                "<script>window.UiContextNew = "
                + json.dumps(context, ensure_ascii=False)
                + ";</script>"
            )

            report = collect_authorized_pages(
                workspace=workspace,
                source_ids=["P00456"],
                authorization_ref="authorization-42",
                fetch_page=lambda source_id: (200, html),
                interval_seconds=60,
                max_pages=1,
            )

            self.assertEqual(["P00456"], report["fetched"])
            public = json.loads(
                (workspace / "problems" / "P00456" / "public-content.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("未标记的公开题干", public["contentLines"])
            self.assertFalse(
                (workspace / "problems" / "P00456" / "problem.json").exists()
            )
            self.assertFalse((workspace / "raw" / "P00456.html").exists())

    def test_collection_state_resumes_without_refetching_completed_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = CollectionState.load(path, ["P00456", "P00457"])
            state.record_fetched("P00456", "abc", 200)
            state.save()

            resumed = CollectionState.load(path, ["P00456", "P00457"])
            self.assertEqual(["P00457"], resumed.pending_ids())
            self.assertEqual("abc", resumed.entries["P00456"]["sha256"])

    def test_collection_fetches_pending_pages_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fetched = []
            sleeps = []
            now_values = iter([0.0, 0.0, 1.0, 60.0])

            def fetch(source_id):
                fetched.append(source_id)
                return 200, SYNTHETIC_HTML.replace("P00456", source_id)

            first = collect_authorized_pages(
                workspace=workspace,
                source_ids=["P00456", "P00457"],
                authorization_ref="authorization-42",
                fetch_page=fetch,
                interval_seconds=60,
                sleep=sleeps.append,
                now=lambda: next(now_values),
                max_pages=1,
            )
            second = collect_authorized_pages(
                workspace=workspace,
                source_ids=["P00456", "P00457"],
                authorization_ref="authorization-42",
                fetch_page=fetch,
                interval_seconds=60,
                sleep=sleeps.append,
                now=lambda: next(now_values),
                max_pages=1,
            )

            self.assertEqual(["P00456"], first["fetched"])
            self.assertEqual(["P00457"], second["fetched"])
            self.assertEqual(["P00456", "P00457"], fetched)
            self.assertEqual([59.0], sleeps)
            self.assertFalse((workspace / "raw" / "P00456.html").exists())
            self.assertTrue(
                (workspace / "problems" / "P00457" / "public-content.json").exists()
            )
            self.assertFalse(
                (workspace / "problems" / "P00457" / "problem.json").exists()
            )

    def test_collection_state_ignores_entries_outside_current_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = CollectionState.load(path, ["P00456", "P00457"])
            state.save()

            narrowed = CollectionState.load(path, ["P00457"])

            self.assertEqual(["P00457"], narrowed.pending_ids())
            self.assertNotIn("P00456", narrowed.entries)

    def test_collection_enforces_cooldown_across_process_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            now_values = iter([1000.0, 1000.0, 1001.0, 2200.0])
            sleeps = []
            fetch = lambda source_id: (
                200,
                SYNTHETIC_HTML.replace("P00456", source_id),
            )
            collect_authorized_pages(
                workspace,
                ["P00456", "P00457"],
                "authorization-42",
                fetch,
                sleep=sleeps.append,
                now=lambda: next(now_values),
                max_pages=1,
            )
            collect_authorized_pages(
                workspace,
                ["P00456", "P00457"],
                "authorization-42",
                fetch,
                sleep=sleeps.append,
                now=lambda: next(now_values),
                max_pages=1,
            )

            self.assertEqual([59.0], sleeps)

    def test_collection_sleeps_between_pages(self):
        sleeps = []
        now_values = iter([0.0, 0.0, 1.0, 60.0])
        with tempfile.TemporaryDirectory() as directory:
            collect_authorized_pages(
                workspace=Path(directory),
                source_ids=["P00456", "P00457"],
                authorization_ref="authorization-42",
                fetch_page=lambda source_id: (
                    200,
                    SYNTHETIC_HTML.replace("P00456", source_id),
                ),
                interval_seconds=60,
                sleep=sleeps.append,
                now=lambda: next(now_values),
            )
        self.assertEqual([59.0], sleeps)

    def test_collection_rejects_interval_below_minimum_before_fetch(self):
        fetched = []

        def fetch(source_id):
            fetched.append(source_id)
            return 200, SYNTHETIC_HTML

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "shorter than 60 seconds"):
                collect_authorized_pages(
                    workspace=Path(directory),
                    source_ids=["P00456"],
                    authorization_ref="authorization-42",
                    fetch_page=fetch,
                    interval_seconds=59,
                )

        self.assertEqual([], fetched)

    def test_collection_halts_on_login_or_rate_limit(self):
        for status, body in ((429, "slow down"), (200, "<title>Login</title>")):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(CollectionHalted):
                    collect_authorized_pages(
                        workspace=Path(directory),
                        source_ids=["P00456"],
                        authorization_ref="authorization-42",
                        fetch_page=lambda source_id: (status, body),
                        interval_seconds=60,
                        sleep=lambda seconds: None,
                    )

    def test_browser_environment_requires_existing_local_installations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "playwright"
            browser = root / "firefox"
            module.mkdir()
            browser.write_text("binary", encoding="utf-8")

            self.assertEqual(
                (module, browser),
                validate_browser_environment(str(module), str(browser)),
            )
            with self.assertRaises(FileNotFoundError):
                validate_browser_environment(str(root / "missing"), str(browser))

    def test_plan_accepts_only_approved_verified_problem_with_tests(self):
        problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")
        problem["workflowState"] = "human-approved"
        problem["verification"] = {"passed": True, "reportSha256": "a" * 64}
        problem["testCases"] = [{"input": "2\n", "output": "3\n"}]

        plan = build_import_plan([problem], ["P00456"], "authorization-42", MAPPING)
        self.assertEqual(1, plan["acceptedCount"])
        self.assertEqual(0, plan["rejectedCount"])
        self.assertEqual("P00456", plan["accepted"][0]["sourceId"])
        self.assertEqual("DRAFT", plan["accepted"][0]["status"])
        self.assertTrue(plan["accepted"][0]["exactlyMatch"])
        self.assertEqual(456, plan["accepted"][0]["targetProblemId"])
        self.assertEqual(2, plan["schemaVersion"])
        self.assertEqual(MAPPING.sha256, plan["mappingSha256"])
        self.assertEqual(64, len(plan["planSha256"]))

    def test_import_content_digest_ignores_workflow_metadata_but_tracks_persisted_content(self):
        problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")
        problem["workflowState"] = "human-approved"
        problem["verification"] = {"passed": True, "reportSha256": "a" * 64}
        problem["testCases"] = [{"input": "2", "output": "3"}]
        first = build_import_plan([problem], ["P00456"], "authorization-42", MAPPING)
        problem["verification"]["reportSha256"] = "b" * 64
        second = build_import_plan([problem], ["P00456"], "authorization-42", MAPPING)
        problem["tags"] = ["数组", "不同标签"]
        third = build_import_plan([problem], ["P00456"], "authorization-42", MAPPING)
        self.assertEqual(
            first["accepted"][0]["contentSha256"],
            second["accepted"][0]["contentSha256"],
        )
        self.assertNotEqual(
            second["accepted"][0]["contentSha256"],
            third["accepted"][0]["contentSha256"],
        )

    def test_plan_reports_missing_and_unapproved_problems(self):
        problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")

        plan = build_import_plan(
            [problem], ["P00456", "P00457"], "authorization-42", MAPPING
        )

        self.assertEqual(0, plan["acceptedCount"])
        rejection_codes = {
            code
            for rejection in plan["rejected"]
            for code in rejection["codes"]
        }
        self.assertEqual(
            {"not-approved", "verification-failed", "missing-tests", "missing-source"},
            rejection_codes,
        )

    def test_plan_rejects_unverified_or_unsupported_judging(self):
        problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")
        problem["workflowState"] = "human-approved"
        problem["verification"] = {"passed": False, "reportSha256": "b" * 64}
        problem["testCases"] = [{"input": "2", "output": "3"}]
        problem["judgeMode"] = "special"

        plan = build_import_plan([problem], ["P00456"], "authorization-42", MAPPING)
        self.assertEqual(0, plan["acceptedCount"])
        codes = set(plan["rejected"][0]["codes"])
        self.assertEqual({"verification-failed", "unsupported-judge"}, codes)

    def test_browser_command_uses_existing_paths_without_install_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "playwright"
            browser = root / "firefox"
            script = root / "fetch.mjs"
            module.mkdir()
            browser.write_text("binary", encoding="utf-8")
            script.write_text("// synthetic", encoding="utf-8")

            command = build_browser_command(
                script,
                module,
                browser,
                "P00456",
            )

            self.assertEqual("node", command[0])
            self.assertIn(str(browser), command)
            self.assertNotIn("install", command)
            self.assertEqual("P00456", command[-1])

    def test_browser_fetch_returns_structured_page_result(self):
        class Result:
            returncode = 0
            stdout = json.dumps({"status": 200, "html": SYNTHETIC_HTML})
            stderr = ""

        calls = []

        def run(command, **options):
            calls.append((command, options))
            return Result()

        status, html = fetch_problem_page(
            source_id="P00456",
            script_path=Path("/tmp/fetch.mjs"),
            playwright_module_path=Path("/tmp/playwright"),
            browser_executable_path=Path("/tmp/firefox"),
            run=run,
        )

        self.assertEqual(200, status)
        self.assertEqual(SYNTHETIC_HTML, html)
        self.assertEqual("P00456", calls[0][0][-1])
        self.assertTrue(calls[0][1]["check"] is False)
        self.assertEqual(2100, calls[0][1]["timeout"])

    def test_browser_fetch_accepts_authorized_boundaries(self):
        calls = []

        class SuccessResult:
            returncode = 0
            stdout = json.dumps({"status": 200, "html": SYNTHETIC_HTML})
            stderr = ""

        def run(command, **options):
            calls.append(command[-1])
            return SuccessResult()

        for source_id in ("P00000", "P10000"):
            with self.subTest(source_id=source_id):
                status, html = fetch_problem_page(
                    source_id,
                    Path("/tmp/fetch.mjs"),
                    Path("/tmp/playwright"),
                    Path("/tmp/firefox"),
                    run=run,
                )
                self.assertEqual(200, status)
                self.assertEqual(SYNTHETIC_HTML, html)

        self.assertEqual(["P00000", "P10000"], calls)

    def test_browser_fetch_rejects_out_of_scope_id_and_process_failure(self):
        for source_id in ("P10001", "P0000", "Q00000", "P100000"):
            with self.subTest(source_id=source_id):
                with self.assertRaises(ValueError):
                    fetch_problem_page(
                        source_id,
                        Path("/tmp/fetch.mjs"),
                        Path("/tmp/playwright"),
                        Path("/tmp/firefox"),
                        run=lambda command, **options: self.fail("runner must not execute"),
                    )

        class FailedResult:
            returncode = 2
            stdout = ""
            stderr = "authentication required"

        with self.assertRaisesRegex(BrowserFetchError, "authentication required"):
            fetch_problem_page(
                "P00456",
                Path("/tmp/fetch.mjs"),
                Path("/tmp/playwright"),
                Path("/tmp/firefox"),
                run=lambda command, **options: FailedResult(),
            )

    def test_node_browser_script_uses_exact_authorized_url_and_blocks_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "playwright"
            module.mkdir()
            (module / "package.json").write_text(
                json.dumps({"type": "module", "main": "index.js"}), encoding="utf-8"
            )
            (module / "index.js").write_text(
                """let attempts = 0;
export const firefox = { launch: async options => ({
  newPage: async () => ({
    route: async (_pattern, handler) => {
      const route = { request: () => ({ resourceType: () => 'document', url: () => 'https://hydro.ac/files/private.zip' }), abort: async () => process.stderr.write('blocked\\n') };
      await handler(route);
    },
    goto: async url => {
      process.stderr.write(url + '\\n');
      if (url.includes('cn-hz.hydrooj.com')) {
        const error = new Error('synthetic timeout');
        error.name = 'TimeoutError';
        throw error;
      }
      return { status: () => 200 };
    },
    title: async () => 'Problem Detail',
    waitForFunction: async (_predicate, sourceId, options) => process.stderr.write(`waited ${sourceId} ${options.timeout}\\n`),
    content: async () => '<html>synthetic</html>',
    close: async () => process.stderr.write('page closed\\n')
  }),
  close: async () => process.stderr.write(options.executablePath + '\\n')
})};""",
                encoding="utf-8",
            )
            browser = root / "firefox"
            browser.write_text("binary", encoding="utf-8")
            script = Path(__file__).parents[1] / "problem_pipeline" / "fetch_hydro_page.mjs"

            for source_id in ("P00000", "P10000"):
                with self.subTest(source_id=source_id):
                    result = subprocess.run(
                        build_browser_command(script, module, browser, source_id),
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(
                        {"status": 200, "html": "<html>synthetic</html>"},
                        json.loads(result.stdout),
                    )
                    self.assertIn(
                        f"https://cn-hz.hydrooj.com/d/hwod_oj/p/{source_id}",
                        result.stderr,
                    )
                    self.assertIn("blocked", result.stderr)
                    self.assertIn(f"waited {source_id} 60000", result.stderr)
                    self.assertIn(str(browser), result.stderr)

            for source_id in ("P10001", "P0000", "P100000", "Q00000"):
                with self.subTest(source_id=source_id):
                    result = subprocess.run(
                        build_browser_command(script, module, browser, source_id),
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("outside the authorized range", result.stderr)

    def test_cli_plan_writes_deterministic_report_and_fails_when_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            problems = root / "problems"
            problems.mkdir()
            problem = parse_problem_html(SYNTHETIC_HTML, "P00456", "authorization-42")
            (problems / "P00456.json").write_text(
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
                    "--range",
                    "P00456-P00457",
                    "--authorization-ref",
                    "authorization-42",
                    "--mapping",
                    str(mapping),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(2, result.returncode, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, report["acceptedCount"])
            self.assertEqual(2, report["rejectedCount"])

    def test_cli_collect_runs_one_authorized_page_with_local_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "playwright"
            module.mkdir()
            (module / "package.json").write_text(
                json.dumps({"type": "module", "main": "index.js"}), encoding="utf-8"
            )
            synthetic_html = json.dumps(SYNTHETIC_HTML.replace("P00456", "P00000"))
            (module / "index.js").write_text(
                f"""export const firefox = {{ launch: async () => ({{
  newPage: async () => ({{
    route: async () => {{}},
    goto: async () => ({{ status: () => 200 }}),
    title: async () => 'Problem Detail',
    waitForFunction: async () => {{}},
    content: async () => {synthetic_html},
    close: async () => {{}}
  }}),
  close: async () => {{}}
}}) }};""",
                encoding="utf-8",
            )
            browser = root / "firefox"
            browser.write_text("binary", encoding="utf-8")
            workspace = root / "workspace"

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.problem_pipeline.cli",
                    "collect",
                    "--workspace",
                    str(workspace),
                    "--range",
                    "P00000-P00000",
                    "--authorization-ref",
                    "authorization-42",
                    "--playwright",
                    str(module),
                    "--browser",
                    str(browser),
                    "--max-pages",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(["P00000"], report["fetched"])
            self.assertEqual(60, report["intervalSeconds"])
            public_content = json.loads(
                (workspace / "problems" / "P00000" / "public-content.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("P00000", public_content["sourceId"])
            self.assertFalse(
                (workspace / "problems" / "P00000" / "problem.json").exists()
            )

    def test_differential_verification_is_reproducible(self):
        def cases(random):
            return [random.randint(-20, 20) for _ in range(100)]

        report = differential_verify(
            reference=lambda value: value * value,
            oracle=lambda value: sum(value for _ in range(abs(value)))
            if value >= 0
            else value * value,
            case_factory=cases,
            seed=20260804,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(100, report["caseCount"])
        self.assertEqual(report, differential_verify(
            reference=lambda value: value * value,
            oracle=lambda value: sum(value for _ in range(abs(value)))
            if value >= 0
            else value * value,
            case_factory=cases,
            seed=20260804,
        ))

    def test_differential_verification_catches_wrong_reference(self):
        report = differential_verify(
            reference=lambda value: value + 1,
            oracle=lambda value: value,
            case_factory=lambda random: [0, 1, random.randint(2, 10)],
            seed=7,
        )

        self.assertFalse(report["passed"])
        self.assertEqual(0, report["firstFailure"]["caseIndex"])
        self.assertNotIn("case", report["firstFailure"])

    def test_rejects_judge_modes_voj_cannot_represent(self):
        require_supported_judge("default")
        for mode in ("interactive", "special", "output-only", "float"):
            with self.subTest(mode=mode), self.assertRaises(CompatibilityError):
                require_supported_judge(mode)


if __name__ == "__main__":
    unittest.main()
