import hashlib
import random
from collections.abc import Callable
from typing import Any


class CompatibilityError(ValueError):
    pass


def require_supported_judge(mode: str) -> None:
    if mode.lower() not in {"default", "exact", "standard"}:
        raise CompatibilityError(f"unsupported judge mode: {mode}")


def _result_digest(value: Any) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def differential_verify(
    reference: Callable[[Any], Any],
    oracle: Callable[[Any], Any],
    case_factory: Callable[[random.Random], list[Any]],
    seed: int,
) -> dict[str, Any]:
    cases = case_factory(random.Random(seed))
    for index, case in enumerate(cases):
        expected = oracle(case)
        actual = reference(case)
        if actual != expected:
            return {
                "schemaVersion": 1,
                "seed": seed,
                "caseCount": len(cases),
                "passed": False,
                "firstFailure": {
                    "caseIndex": index,
                    "expectedSha256": _result_digest(expected),
                    "actualSha256": _result_digest(actual),
                },
            }
    return {
        "schemaVersion": 1,
        "seed": seed,
        "caseCount": len(cases),
        "passed": True,
    }
