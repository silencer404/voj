import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import content_digest


_SOURCE_ID = re.compile(r"P(\d{5})")
_REQUIRED_MAPPING = {
    "schemaVersion": 1,
    "sourceIdRange": "P00000-P10000",
    "targetProblemIdStart": 0,
}


@dataclass(frozen=True)
class ProblemMapping:
    value: dict[str, Any]
    sha256: str

    def target_problem_id(self, source_id: str) -> int:
        match = _SOURCE_ID.fullmatch(source_id)
        if match is None:
            raise ValueError(f"invalid source id: {source_id}")
        source_number = int(match.group(1))
        if source_number > 10000:
            raise ValueError(f"source id outside mapping: {source_id}")
        return source_number


def load_problem_mapping(path: Path) -> ProblemMapping:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid problem mapping: {path}") from error
    if not isinstance(value, dict) or value != _REQUIRED_MAPPING:
        raise ValueError("unsupported problem mapping policy")
    return ProblemMapping(value=value, sha256=content_digest(value))
