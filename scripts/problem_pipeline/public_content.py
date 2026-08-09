import hashlib
import json
from pathlib import Path
from typing import Any


PUBLIC_CONTENT_SCHEMA_VERSION = 1


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_public_content(
    *,
    source_system: str,
    source_domain: str,
    source_id: str,
    source_url: str,
    authorization_ref: str,
    title: str,
    statement: str,
    time_limit_ms: int,
    memory_limit_kb: int,
    judge_mode: str,
    tags: list[str],
) -> dict[str, Any]:
    normalized_title = normalize_text(title).strip()
    normalized_statement = normalize_text(statement)
    if not normalized_title or not normalized_statement:
        raise ValueError("public problem title and statement are required")
    payload: dict[str, Any] = {
        "schemaVersion": PUBLIC_CONTENT_SCHEMA_VERSION,
        "sourceSystem": source_system,
        "sourceDomain": source_domain,
        "sourceId": source_id,
        "sourceUrl": source_url,
        "authorizationRef": authorization_ref,
        "title": normalized_title,
        "contentLines": normalized_statement.split("\n"),
        "timeLimitMs": time_limit_ms,
        "memoryLimitKb": memory_limit_kb,
        "judgeMode": judge_mode,
        "tags": tags,
    }
    payload["publicContentSha256"] = _digest(payload)
    return payload


def validate_public_content(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("public content must be an object")
    expected = {
        "schemaVersion",
        "sourceSystem",
        "sourceDomain",
        "sourceId",
        "sourceUrl",
        "authorizationRef",
        "title",
        "contentLines",
        "timeLimitMs",
        "memoryLimitKb",
        "judgeMode",
        "tags",
        "publicContentSha256",
    }
    if set(value) != expected:
        raise ValueError("public content fields are invalid")
    without_digest = dict(value)
    digest = without_digest.pop("publicContentSha256")
    if value["schemaVersion"] != PUBLIC_CONTENT_SCHEMA_VERSION or digest != _digest(without_digest):
        raise ValueError("public content digest is invalid")
    string_fields = (
        "sourceSystem",
        "sourceDomain",
        "sourceId",
        "sourceUrl",
        "authorizationRef",
        "title",
        "judgeMode",
    )
    if any(not isinstance(value[field], str) for field in string_fields):
        raise ValueError("public content string field is invalid")
    if not value["title"].strip() or not value["authorizationRef"].strip():
        raise ValueError("public content metadata is incomplete")
    lines = value["contentLines"]
    if not isinstance(lines, list) or not lines or any(not isinstance(line, str) for line in lines):
        raise ValueError("public content lines are invalid")
    if not any(line.strip() for line in lines):
        raise ValueError("public problem statement is empty")
    if type(value["timeLimitMs"]) is not int or value["timeLimitMs"] <= 0:
        raise ValueError("public content time limit is invalid")
    if type(value["memoryLimitKb"]) is not int or value["memoryLimitKb"] <= 0:
        raise ValueError("public content memory limit is invalid")
    if not isinstance(value["tags"], list) or any(not isinstance(tag, str) for tag in value["tags"]):
        raise ValueError("public content tags are invalid")
    return value


def load_public_content(path: Path) -> dict[str, Any]:
    return validate_public_content(json.loads(path.read_text(encoding="utf-8")))


def write_public_content(path: Path, value: dict[str, Any]) -> None:
    validate_public_content(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build_manual_public_content(
    source_id: str,
    authorization_ref: str,
    title_path: Path,
    statement_path: Path,
) -> dict[str, Any]:
    if not authorization_ref.startswith("user-provided:"):
        raise ValueError("manual authorization reference must use user-provided: prefix")
    title = title_path.read_text(encoding="utf-8")
    statement = statement_path.read_text(encoding="utf-8")
    if len([line for line in normalize_text(title).splitlines() if line.strip()]) != 1:
        raise ValueError("manual title file must contain exactly one non-empty line")
    return build_public_content(
        source_system="manual",
        source_domain="user-provided",
        source_id=source_id,
        source_url="",
        authorization_ref=authorization_ref,
        title=title,
        statement=statement,
        time_limit_ms=1000,
        memory_limit_kb=262144,
        judge_mode="default",
        tags=[],
    )
