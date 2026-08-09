import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .public_content import build_public_content


MIN_SOURCE_NUMBER = 0
MAX_SOURCE_NUMBER = 10_000
AUTHORIZED_SOURCE_RANGE = "P00000-P10000"
CONTEXT_PREFIX = "window.UiContextNew = "


class HydroParseError(ValueError):
    pass


def validate_source_id(source_id: str) -> None:
    match = re.fullmatch(r"P([0-9]{5})", source_id)
    if not match or not MIN_SOURCE_NUMBER <= int(match.group(1)) <= MAX_SOURCE_NUMBER:
        raise ValueError(f"source id is outside the authorized {AUTHORIZED_SOURCE_RANGE} interval")


def expand_source_range(value: str) -> list[str]:
    match = re.fullmatch(r"P([0-9]{5})-P([0-9]{5})", value)
    if not match:
        raise ValueError("source range must use P00000-P00000 format")
    start, end = (int(part) for part in match.groups())
    if start < MIN_SOURCE_NUMBER or end > MAX_SOURCE_NUMBER or start > end:
        raise ValueError(f"source range is outside the authorized {AUTHORIZED_SOURCE_RANGE} interval")
    return [f"P{number:05d}" for number in range(start, end + 1)]


def _decode_single_quoted_string(value: str) -> str:
    result: list[str] = []
    index = 1
    escapes = {
        "'": "'",
        '"': '"',
        "\\": "\\",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while index < len(value):
        character = value[index]
        if character == "'":
            return "".join(result)
        if character != "\\":
            result.append(character)
            index += 1
            continue
        index += 1
        if index >= len(value):
            break
        escape = value[index]
        if escape in escapes:
            result.append(escapes[escape])
            index += 1
        elif escape == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", value[index + 1:index + 5]):
            result.append(chr(int(value[index + 1:index + 5], 16)))
            index += 5
        elif escape == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", value[index + 1:index + 3]):
            result.append(chr(int(value[index + 1:index + 3], 16)))
            index += 3
        elif escape == "\n":
            index += 1
        elif escape == "\r":
            index += 2 if index + 1 < len(value) and value[index + 1] == "\n" else 1
        else:
            raise HydroParseError("public problem context string is malformed")
    raise HydroParseError("public problem context string is unterminated")


def _extract_context(html: str) -> dict[str, Any]:
    start = html.find(CONTEXT_PREFIX)
    if start < 0:
        raise HydroParseError("public problem context is missing")
    encoded = html[start + len(CONTEXT_PREFIX):].lstrip()
    decoder = json.JSONDecoder()
    try:
        context, _ = decoder.raw_decode(encoded)
    except json.JSONDecodeError as error:
        if not encoded.startswith("'"):
            raise HydroParseError("public problem context is malformed") from error
        try:
            context = json.loads(_decode_single_quoted_string(encoded))
        except json.JSONDecodeError as nested_error:
            raise HydroParseError("public problem context is malformed") from nested_error
    if not isinstance(context, dict) or not isinstance(context.get("pdoc"), dict):
        raise HydroParseError("problem document is missing")
    return context


def _localized_content(raw: Any) -> str:
    if not isinstance(raw, str):
        raise HydroParseError("problem content is missing")
    try:
        localized = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(localized, dict):
        raise HydroParseError("localized problem content is malformed")
    for key in ("zh", "zh_CN", "en"):
        value = localized.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise HydroParseError("supported localized problem content is missing")


def _section(content: str, title: str, following: tuple[str, ...]) -> str:
    start_match = re.search(rf"(?m)^##\s*{re.escape(title)}\s*$", content)
    if not start_match:
        raise HydroParseError(f"section is missing: {title}")
    end = len(content)
    for next_title in following:
        next_match = re.search(
            rf"(?m)^##\s*{re.escape(next_title)}\s*$", content[start_match.end():]
        )
        if next_match:
            end = min(end, start_match.end() + next_match.start())
    return content[start_match.end():end].strip()


def _sample(content: str, kind: str) -> str:
    match = re.search(rf"```{kind}\d*\s*\n(.*?)```", content, flags=re.DOTALL)
    if not match:
        raise HydroParseError(f"sample is missing: {kind}")
    return match.group(1).strip()


def _legacy_sections(content: str) -> tuple[str, str, str, str, str]:
    fenced = re.fullmatch(r"\s*```markdown\s*\n(.*?)\n```\s*", content, re.DOTALL)
    if not fenced:
        raise HydroParseError("legacy problem structure is malformed")
    lines = fenced.group(1).splitlines()

    def marker_index(label: str, start: int = 0, end: int | None = None) -> int:
        limit = len(lines) if end is None else end
        matches = [
            index for index in range(start, limit) if lines[index].strip() == label
        ]
        if len(matches) != 1:
            raise HydroParseError(f"legacy marker is missing or duplicated: {label}")
        return matches[0]

    input_description = marker_index("输入描述")
    output_description = marker_index("输出描述", input_description + 1)
    first_sample = marker_index("样例 1", output_description + 1)
    later_samples = [
        index
        for index in range(first_sample + 1, len(lines))
        if re.fullmatch(r"样例 [2-9][0-9]*", lines[index].strip())
    ]
    first_sample_end = later_samples[0] if later_samples else len(lines)
    sample_input_marker = marker_index("输入：", first_sample + 1, first_sample_end)
    sample_output_marker = marker_index(
        "输出：", sample_input_marker + 1, first_sample_end
    )

    sections = (
        "\n".join(lines[:input_description]).strip(),
        "\n".join(lines[input_description + 1:output_description]).strip(),
        "\n".join(lines[output_description + 1:first_sample]).strip(),
        "\n".join(lines[sample_input_marker + 1:sample_output_marker]).strip(),
        "\n".join(lines[sample_output_marker + 1:first_sample_end]).strip(),
    )
    if any(not section for section in sections):
        raise HydroParseError("legacy problem section is empty")
    return sections


def _plain_legacy_sections(content: str) -> tuple[str, str, str, str, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() in {"```markdown", "```md", "```"}:
        raise HydroParseError("plain legacy problem structure is malformed")

    def marker_index(label: str, start: int = 0, end: int | None = None) -> int:
        limit = len(lines) if end is None else end
        matches = [
            index for index in range(start, limit) if lines[index].strip() == label
        ]
        if len(matches) != 1:
            raise HydroParseError(
                f"plain legacy marker is missing or duplicated: {label}"
            )
        return matches[0]

    input_description = marker_index("输入描述")
    output_description = marker_index("输出描述", input_description + 1)
    sample_input_marker = marker_index("输入：", output_description + 1)
    sample_output_marker = marker_index("输出：", sample_input_marker + 1)
    sections = (
        "\n".join(lines[:input_description]).strip(),
        "\n".join(lines[input_description + 1:output_description]).strip(),
        "\n".join(lines[output_description + 1:sample_input_marker]).strip(),
        "\n".join(lines[sample_input_marker + 1:sample_output_marker]).strip(),
        "\n".join(lines[sample_output_marker + 1:]).strip(),
    )
    if any(not section for section in sections):
        raise HydroParseError("plain legacy problem section is empty")
    return sections


def _plain_format_sections(content: str) -> tuple[str, str, str, str, str]:
    lines = content.splitlines()

    def marker_index(label: str, start: int = 0) -> int:
        matches = [
            index for index in range(start, len(lines)) if lines[index].strip() == label
        ]
        if len(matches) != 1:
            raise HydroParseError(
                f"plain format marker is missing or duplicated: {label}"
            )
        return matches[0]

    input_format = marker_index("输入格式")
    output_format = marker_index("输出格式", input_format + 1)
    first_sample = marker_index("示例1", output_format + 1)
    sample_input_marker = marker_index("输入：", first_sample + 1)
    sample_output_marker = marker_index("输出：", sample_input_marker + 1)
    sections = (
        "\n".join(lines[:input_format]).strip(),
        "\n".join(lines[input_format + 1:output_format]).strip(),
        "\n".join(lines[output_format + 1:first_sample]).strip(),
        "\n".join(lines[sample_input_marker + 1:sample_output_marker]).strip(),
        "\n".join(lines[sample_output_marker + 1:]).strip(),
    )
    if any(not section for section in sections):
        raise HydroParseError("plain format problem section is empty")
    return sections


def _plain_description_sample_sections(
    content: str,
    input_description_label: str = "输入描述",
    output_description_label: str = "输出描述",
    sample_input_label: str = "输入",
    sample_output_label: str = "输出",
) -> tuple[str, str, str, str, str]:
    lines = content.splitlines()

    def marker_index(label: str, start: int = 0, end: int | None = None) -> int:
        limit = len(lines) if end is None else end
        matches = [
            index for index in range(start, limit) if lines[index].strip() == label
        ]
        if len(matches) != 1:
            raise HydroParseError(
                f"plain description sample marker is missing or duplicated: {label}"
            )
        return matches[0]

    input_description = marker_index(input_description_label)
    output_description = marker_index(
        output_description_label, input_description + 1
    )
    first_sample = marker_index("示例1", output_description + 1)
    later_samples = [
        index
        for index in range(first_sample + 1, len(lines))
        if re.fullmatch(r"示例[2-9][0-9]*", lines[index].strip())
    ]
    first_sample_end = later_samples[0] if later_samples else len(lines)
    sample_input_marker = marker_index(
        sample_input_label, first_sample + 1, first_sample_end
    )
    sample_output_marker = marker_index(
        sample_output_label, sample_input_marker + 1, first_sample_end
    )
    explanations = [
        index
        for index in range(sample_output_marker + 1, first_sample_end)
        if lines[index].strip() in {"说明", "说明："}
    ]
    sample_output_end = explanations[0] if explanations else first_sample_end
    sections = (
        "\n".join(lines[:input_description]).strip(),
        "\n".join(lines[input_description + 1:output_description]).strip(),
        "\n".join(lines[output_description + 1:first_sample]).strip(),
        "\n".join(lines[sample_input_marker + 1:sample_output_marker]).strip(),
        "\n".join(lines[sample_output_marker + 1:sample_output_end]).strip(),
    )
    if any(not section for section in sections):
        raise HydroParseError("plain description sample section is empty")
    return sections


def _duration_ms(raw: Any) -> int:
    match = re.fullmatch(r"(\d+)(ms|s)", str(raw).lower())
    if not match:
        raise HydroParseError("unsupported time limit")
    value = int(match.group(1))
    return value if match.group(2) == "ms" else value * 1000


def _memory_kb(raw: Any) -> int:
    match = re.fullmatch(r"(\d+)(k|m|g)(?:i?b)?", str(raw).lower())
    if not match:
        raise HydroParseError("unsupported memory limit")
    value = int(match.group(1))
    multiplier = {"k": 1, "m": 1024, "g": 1024 * 1024}[match.group(2)]
    return value * multiplier


def _resource_limits(config: dict[str, Any]) -> tuple[int, int]:
    if config.get("time") is not None or config.get("memory") is not None:
        return _duration_ms(config.get("time")), _memory_kb(config.get("memory"))

    time_min = config.get("timeMin")
    time_max = config.get("timeMax")
    memory_min = config.get("memoryMin")
    memory_max = config.get("memoryMax")
    if not all(
        type(value) is int and value > 0
        for value in (time_min, time_max, memory_min, memory_max)
    ):
        raise HydroParseError("legacy resource limits are malformed")
    assert isinstance(time_min, int)
    assert isinstance(time_max, int)
    assert isinstance(memory_min, int)
    assert isinstance(memory_max, int)
    if time_min > time_max or memory_min > memory_max:
        raise HydroParseError("legacy resource limit range is invalid")
    return time_max, memory_max * 1024


def extract_public_problem(
    html: str, expected_source_id: str, authorization_ref: str
) -> dict[str, Any]:
    document = _extract_context(html)["pdoc"]
    source_id = document.get("pid")
    if source_id != expected_source_id:
        raise HydroParseError("page source id does not match requested source id")
    content = _localized_content(document.get("content"))
    config = document.get("config")
    if not isinstance(config, dict):
        raise HydroParseError("judge configuration is missing")
    time_limit_ms, memory_limit_kb = _resource_limits(config)
    try:
        return build_public_content(
            source_system="hydro",
            source_domain="hwod_oj",
            source_id=source_id,
            source_url=f"https://hydro.ac/d/hwod_oj/p/{source_id}",
            authorization_ref=authorization_ref,
            title=str(document.get("title") or ""),
            statement=content,
            time_limit_ms=time_limit_ms,
            memory_limit_kb=memory_limit_kb,
            judge_mode=str(config.get("type") or "default"),
            tags=[str(tag) for tag in document.get("tag") or []],
        )
    except ValueError as error:
        raise HydroParseError(str(error)) from error


def parse_problem_html(html: str, expected_source_id: str, authorization_ref: str) -> dict[str, Any]:
    document = _extract_context(html)["pdoc"]
    source_id = document.get("pid")
    if source_id != expected_source_id:
        raise HydroParseError("page source id does not match requested source id")
    content = _localized_content(document.get("content"))
    config = document.get("config")
    if not isinstance(config, dict):
        raise HydroParseError("judge configuration is missing")
    if re.fullmatch(r"\s*```markdown\s*\n.*\n```\s*", content, re.DOTALL):
        description, input_format, output_format, sample_input, sample_output = _legacy_sections(content)
    elif not re.search(r"(?m)^##\s*题目描述\s*$", content):
        if re.search(r"(?m)^输入格式\s*$", content):
            description, input_format, output_format, sample_input, sample_output = _plain_format_sections(content)
        elif re.search(r"(?m)^示例1\s*$", content):
            input_description_label = "输入描述：" if re.search(r"(?m)^输入描述：\s*$", content) else "输入描述"
            output_description_label = "输出描述：" if re.search(r"(?m)^输出描述：\s*$", content) else "输出描述"
            sample_input_label = "输入:" if re.search(r"(?m)^输入:\s*$", content) else "输入"
            sample_output_label = "输出：" if re.search(r"(?m)^输出：\s*$", content) else "输出"
            labels = (
                input_description_label,
                output_description_label,
                sample_input_label,
                sample_output_label,
            )
            supported_labels = {
                ("输入描述", "输出描述", "输入", "输出"),
                ("输入描述", "输出描述", "输入:", "输出"),
                ("输入描述", "输出描述", "输入:", "输出："),
                ("输入描述：", "输出描述：", "输入", "输出："),
            }
            if labels not in supported_labels:
                raise HydroParseError("unsupported plain description label combination")
            description, input_format, output_format, sample_input, sample_output = _plain_description_sample_sections(
                content,
                input_description_label=input_description_label,
                output_description_label=output_description_label,
                sample_input_label=sample_input_label,
                sample_output_label=sample_output_label,
            )
        else:
            description, input_format, output_format, sample_input, sample_output = _plain_legacy_sections(content)
    else:
        description = _section(content, "题目描述", ("输入格式",))
        input_format = _section(content, "输入格式", ("输出格式",))
        output_format = _section(content, "输出格式", ("样例", "提示", "说明"))
        output_format = re.split(r"```(?:input|output)\d*", output_format, maxsplit=1)[0].strip()
        sample_input = _sample(content, "input")
        sample_output = _sample(content, "output")
    time_limit_ms, memory_limit_kb = _resource_limits(config)
    return {
        "schemaVersion": 1,
        "sourceSystem": "hydro",
        "sourceDomain": "hwod_oj",
        "sourceId": source_id,
        "sourceUrl": f"https://hydro.ac/d/hwod_oj/p/{source_id}",
        "authorizationRef": authorization_ref,
        "title": str(document.get("title") or "").strip(),
        "description": description,
        "inputFormat": input_format,
        "outputFormat": output_format,
        "sampleInput": sample_input,
        "sampleOutput": sample_output,
        "hint": "",
        "timeLimitMs": time_limit_ms,
        "memoryLimitKb": memory_limit_kb,
        "judgeMode": str(config.get("type") or "default"),
        "tags": [str(tag) for tag in document.get("tag") or []],
        "status": "DRAFT",
        "workflowState": "parsed",
    }


class CollectionState:
    def __init__(
        self,
        path: Path,
        entries: dict[str, dict[str, Any]],
        last_fetched_at: float | None = None,
    ):
        self.path = path
        self.entries = entries
        self.last_fetched_at = last_fetched_at

    @classmethod
    def load(cls, path: Path, source_ids: list[str]) -> "CollectionState":
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            saved_entries = data.get("entries", {})
            last_fetched_at = data.get("lastFetchedAt")
        else:
            saved_entries = {}
            last_fetched_at = None
        entries = {
            source_id: saved_entries.get(source_id, {"status": "pending"})
            for source_id in source_ids
        }
        return cls(path, entries, last_fetched_at)

    def pending_ids(self) -> list[str]:
        completed = {"fetched", "public-content-ready", "normalized"}
        return [
            source_id
            for source_id, entry in sorted(self.entries.items())
            if entry.get("status") not in completed
        ]

    def record_fetched(self, source_id: str, sha256: str, http_status: int) -> None:
        self.entries[source_id] = {
            "status": "public-content-ready",
            "sha256": sha256,
            "httpStatus": http_status,
        }

    def record_html(
        self, source_id: str, html: str, http_status: int, fetched_at: float
    ) -> None:
        self.record_fetched(
            source_id,
            hashlib.sha256(html.encode("utf-8")).hexdigest(),
            http_status,
        )
        self.last_fetched_at = fetched_at

    def record_normalized(self, source_id: str) -> None:
        entry = self.entries.get(source_id)
        if not isinstance(entry, dict) or entry.get("status") not in {
            "fetched",
            "public-content-ready",
            "normalized",
        }:
            raise ValueError("public content must be prepared before normalization")
        entry["status"] = "normalized"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "entries": self.entries,
            "lastFetchedAt": self.last_fetched_at,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
