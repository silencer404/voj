import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .public_content import load_public_content


SEGMENTATION_SCHEMA_VERSION = 1
VALIDATION_SCHEMA_VERSION = 1
MAX_SEGMENTATION_BYTES = 1_000_000
KINDS = {
    "description",
    "inputFormat",
    "outputFormat",
    "hint",
    "sampleInput",
    "sampleOutput",
    "structure",
}
SEGMENT_KEYS = {"kind", "startLine", "endLine", "sampleIndex"}
STRUCTURE_PATTERN = re.compile(
    r"\s*(?:#{1,6}\s+.*|```[A-Za-z0-9_-]*|```|"
    r"(?:题目描述|输入(?:格式|描述)?|输出(?:格式|描述)?|样例\s*\d*|示例\s*\d*|"
    r"提示|说明)\s*[：:]?)\s*"
)


class SegmentationError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SegmentationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_SEGMENTATION_BYTES:
        raise SegmentationError("segmentation result size is invalid")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SegmentationError("segmentation result is not strict JSON") from error
    if not isinstance(value, dict):
        raise SegmentationError("segmentation result must be an object")
    return value, _digest_bytes(raw)


def _range_text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1:end]).strip("\n")


def _merge_parts(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part.strip()).strip()


def _merge_samples(samples: list[dict[str, str]]) -> tuple[str, str]:
    if len(samples) == 1:
        return samples[0]["input"], samples[0]["output"]
    inputs = [f"样例 {index}\n{sample['input']}" for index, sample in enumerate(samples, 1)]
    outputs = [f"样例 {index}\n{sample['output']}" for index, sample in enumerate(samples, 1)]
    return "\n\n".join(inputs), "\n\n".join(outputs)


def validate_segmentation(
    public_content_path: Path,
    segmentation_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    public = load_public_content(public_content_path)
    value, result_digest = _strict_json(segmentation_path)
    if set(value) != {"schemaVersion", "publicContentSha256", "segments"}:
        raise SegmentationError("segmentation root fields are invalid")
    if value["schemaVersion"] != SEGMENTATION_SCHEMA_VERSION:
        raise SegmentationError("segmentation schema version is unsupported")
    if value["publicContentSha256"] != public["publicContentSha256"]:
        raise SegmentationError("segmentation input digest does not match")
    segments = value["segments"]
    if not isinstance(segments, list) or not segments:
        raise SegmentationError("segmentation segments are missing")

    lines = public["contentLines"]
    expected_start = 1
    grouped: dict[str, list[str]] = {
        "description": [],
        "inputFormat": [],
        "outputFormat": [],
        "hint": [],
    }
    sample_parts: dict[int, dict[str, str]] = {}
    sample_events: list[tuple[int, str]] = []
    validated_segments: list[dict[str, Any]] = []

    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != SEGMENT_KEYS:
            raise SegmentationError("segmentation segment fields are invalid")
        kind = segment["kind"]
        start = segment["startLine"]
        end = segment["endLine"]
        sample_index = segment["sampleIndex"]
        if kind not in KINDS:
            raise SegmentationError("segmentation kind is invalid")
        if type(start) is not int or type(end) is not int:
            raise SegmentationError("segmentation line range is invalid")
        if start != expected_start or start < 1 or end < start or end > len(lines):
            raise SegmentationError("segmentation must cover every line exactly once in order")
        expected_start = end + 1
        text = _range_text(lines, start, end)
        if kind == "structure":
            if sample_index is not None or any(
                line.strip() and not STRUCTURE_PATTERN.fullmatch(line)
                for line in lines[start - 1:end]
            ):
                raise SegmentationError("structure segment contains semantic content")
        elif kind in {"sampleInput", "sampleOutput"}:
            if type(sample_index) is not int or sample_index < 1 or not text.strip():
                raise SegmentationError("sample segment metadata is invalid")
            key = "input" if kind == "sampleInput" else "output"
            sample = sample_parts.setdefault(sample_index, {})
            if key in sample:
                raise SegmentationError("sample contains duplicate input or output")
            sample[key] = text
            sample_events.append((sample_index, key))
        else:
            if sample_index is not None or not text.strip():
                raise SegmentationError("problem segment metadata is invalid")
            grouped[kind].append(text)
        validated_segments.append(dict(segment))

    if expected_start != len(lines) + 1:
        raise SegmentationError("segmentation does not cover the complete public content")
    for required in ("description", "inputFormat", "outputFormat"):
        if not grouped[required]:
            raise SegmentationError(f"required problem segment is missing: {required}")
    indexes = sorted(sample_parts)
    if indexes != list(range(1, len(indexes) + 1)):
        raise SegmentationError("sample indexes must be consecutive from one")
    expected_events = [
        event for index in indexes for event in ((index, "input"), (index, "output"))
    ]
    if sample_events != expected_events:
        raise SegmentationError("sample input and output segments are out of order")
    samples: list[dict[str, str]] = []
    for index in indexes:
        sample = sample_parts[index]
        if set(sample) != {"input", "output"}:
            raise SegmentationError("every sample must contain input and output")
        samples.append(sample)
    if not samples:
        raise SegmentationError("at least one public sample is required")

    sample_input, sample_output = _merge_samples(samples)
    problem = {
        "schemaVersion": 1,
        "sourceSystem": public["sourceSystem"],
        "sourceDomain": public["sourceDomain"],
        "sourceId": public["sourceId"],
        "sourceUrl": public["sourceUrl"],
        "authorizationRef": public["authorizationRef"],
        "title": public["title"],
        "description": _merge_parts(grouped["description"]),
        "inputFormat": _merge_parts(grouped["inputFormat"]),
        "outputFormat": _merge_parts(grouped["outputFormat"]),
        "sampleInput": sample_input,
        "sampleOutput": sample_output,
        "hint": _merge_parts(grouped["hint"]),
        "timeLimitMs": public["timeLimitMs"],
        "memoryLimitKb": public["memoryLimitKb"],
        "judgeMode": public["judgeMode"],
        "tags": public["tags"],
        "status": "DRAFT",
        "workflowState": "parsed",
    }
    validation = {
        "schemaVersion": VALIDATION_SCHEMA_VERSION,
        "publicContentSha256": public["publicContentSha256"],
        "segmentationSha256": result_digest,
        "sampleCount": len(samples),
        "segments": validated_segments,
        "passed": True,
    }
    return problem, validation


def write_validated_problem(problem_directory: Path) -> dict[str, Any]:
    problem, validation = validate_segmentation(
        problem_directory / "public-content.json",
        problem_directory / "segmentation.json",
    )
    (problem_directory / "segmentation-validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (problem_directory / "problem.json").write_text(
        json.dumps(problem, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return validation
