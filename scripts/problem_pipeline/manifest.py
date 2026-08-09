import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_manifest(problems: list[dict[str, Any]], authorization_ref: str) -> dict[str, Any]:
    ordered = sorted(problems, key=lambda problem: problem["sourceId"])
    entries = [
        {
            "sourceId": problem["sourceId"],
            "contentSha256": content_digest(problem),
        }
        for problem in ordered
    ]
    manifest = {
        "schemaVersion": 1,
        "sourceSystem": "hydro",
        "authorizationRef": authorization_ref,
        "problemCount": len(entries),
        "problems": entries,
    }
    manifest["manifestSha256"] = content_digest(manifest)
    return manifest
