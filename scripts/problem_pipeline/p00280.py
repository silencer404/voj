import random
from typing import Any

from .manifest import content_digest
from .verification import differential_verify


def pattern_matches_reference(pattern: str, imsi: str) -> bool:
    reachable = {0}
    for token in pattern:
        next_reachable: set[int] = set()
        if token == "*":
            for index in reachable:
                next_reachable.update(range(index, len(imsi) + 1))
        else:
            for index in reachable:
                if index >= len(imsi):
                    continue
                if token == "?" and index % 2 == 1:
                    next_reachable.add(index + 1)
                elif token == imsi[index]:
                    next_reachable.add(index + 1)
        reachable = next_reachable
    return len(imsi) in reachable


def pattern_matches_oracle(pattern: str, imsi: str) -> bool:
    star_lengths = range(len(imsi) + 1) if "*" in pattern else (0,)
    for star_length in star_lengths:
        expanded = pattern.replace("*", "#" * star_length)
        if len(expanded) != len(imsi):
            continue
        matches = True
        for index, (token, digit) in enumerate(zip(expanded, imsi)):
            if token == "#":
                continue
            if token == "?":
                if index % 2 == 0:
                    matches = False
                    break
            elif token != digit:
                matches = False
                break
        if matches:
            return True
    return False


def solve_reference(instance: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            pattern
            for pattern in instance["patterns"]
            if pattern_matches_reference(pattern, instance["imsi"])
        )
    )


def solve_oracle(instance: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            pattern
            for pattern in instance["patterns"]
            if pattern_matches_oracle(pattern, instance["imsi"])
        )
    )


def _case(name: str, patterns: list[str], imsi: str) -> dict[str, Any]:
    instance = {"patterns": patterns, "imsi": imsi}
    matches = solve_oracle(instance)
    return {
        "name": name,
        "instance": instance,
        "input": f"{','.join(patterns)}\n{imsi}",
        "output": ",".join(matches) if matches else "null",
    }


def _random_pattern(generator: random.Random) -> str:
    length = generator.randint(1, 20)
    star_index = generator.randrange(length) if generator.random() < 0.55 else -1
    tokens = []
    for index in range(length):
        if index == star_index:
            tokens.append("*")
        elif generator.random() < 0.3:
            tokens.append("?")
        else:
            tokens.append(str(generator.randrange(10)))
    return "".join(tokens)


def build_p00280_cases(seed: int, random_count: int) -> list[dict[str, Any]]:
    imsi = "123456789012345"
    cases = [
        _case("sample-star-suffix", ["1234567", "1234567*"], imsi),
        _case("sample-question-index-restriction", ["123?????????345", "123????*????345"], imsi),
        _case("exact-match", [imsi, "123456789012344"], imsi),
        _case("star-empty", [f"{imsi}*", f"*{imsi}"], imsi),
        _case("star-whole-imsi", ["*", "9*", "*5"], imsi),
        _case("star-middle", ["123*345", "123*346", "124*345"], imsi),
        _case("question-at-odd-index", ["1?3456789012345", "?23456789012345"], imsi),
        _case("question-after-star", ["123*?345", "123*4?", "*?"], imsi),
        _case("lexicographic-order", ["123*", "*345", "123456789012345", "*"], imsi),
        _case("pattern-too-long", ["1234567890123456", "????????????????"], imsi),
        _case("no-match", ["0*", "*0", "987654321098765"], imsi),
        _case("maximum-list-length", [str(index % 10) + "*" for index in range(199)], imsi),
    ]

    generator = random.Random(seed)
    for index in range(random_count):
        random_imsi = "".join(str(generator.randrange(10)) for _ in range(15))
        pattern_count = generator.randint(1, 40)
        patterns = [_random_pattern(generator) for _ in range(pattern_count)]
        cases.append(_case(f"random-{index:03d}", patterns, random_imsi))
    return cases


def verify_p00280(seed: int, random_count: int) -> dict[str, Any]:
    cases = build_p00280_cases(seed, random_count)
    return differential_verify(
        reference=solve_reference,
        oracle=solve_oracle,
        case_factory=lambda _random: [case["instance"] for case in cases],
        seed=seed,
    )


def build_p00280_problem(authorization_ref: str, seed: int, random_count: int) -> dict[str, Any]:
    cases = build_p00280_cases(seed, random_count)
    verification = verify_p00280(seed, random_count)
    verification["reportSha256"] = content_digest(verification)
    return {
        "schemaVersion": 1,
        "sourceSystem": "manual",
        "sourceDomain": "user-provided",
        "sourceId": "P00280",
        "sourceUrl": "",
        "authorizationRef": authorization_ref,
        "title": "国际移动用户识别码（IMSI）匹配",
        "description": (
            "给定一个网络配置列表和一个长度为 15 的 IMSI。配置仅包含数字、星号和问号：星号匹配零个或连续多个任意字符；"
            "问号匹配一个字符，但它在 IMSI 中对应的下标必须为奇数，下标从 0 开始。筛选所有能完整匹配 IMSI 的配置。"
        ),
        "inputFormat": (
            "输入共两行。第一行是网络配置列表，各配置以英文逗号分隔；列表长度小于 200，每个配置至多包含一个星号。"
            "第二行是仅由数字组成、长度为 15 的 IMSI。"
        ),
        "outputFormat": (
            "将所有匹配的配置按字典序升序排列，并以英文逗号连接后输出；若没有配置匹配，则输出 null。"
        ),
        "sampleInput": "1234567,1234567*\n123456789012345",
        "sampleOutput": "1234567*",
        "hint": "匹配必须覆盖完整 IMSI；问号对应位置的奇偶性按 IMSI 的绝对下标判断。",
        "timeLimitMs": 1000,
        "memoryLimitKb": 262144,
        "judgeMode": "default",
        "tags": ["字符串", "通配符匹配", "动态规划"],
        "status": "DRAFT",
        "workflowState": "human-approved",
        "verification": verification,
        "testCases": [{"input": case["input"], "output": case["output"]} for case in cases],
    }
