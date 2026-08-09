import random
from typing import Any

from .manifest import content_digest
from .verification import differential_verify


BOARD_SIZE = 19
DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def liberty_sets_reference(instance: dict[str, Any]) -> tuple[int, int]:
    black = set(instance["black"])
    white = set(instance["white"])
    occupied = black | white

    def liberties(stones: set[tuple[int, int]]) -> int:
        empty_neighbors = set()
        for row, column in stones:
            for row_delta, column_delta in DIRECTIONS:
                neighbor = (row + row_delta, column + column_delta)
                if (
                    0 <= neighbor[0] < BOARD_SIZE
                    and 0 <= neighbor[1] < BOARD_SIZE
                    and neighbor not in occupied
                ):
                    empty_neighbors.add(neighbor)
        return len(empty_neighbors)

    return liberties(black), liberties(white)


def empty_point_oracle(instance: dict[str, Any]) -> tuple[int, int]:
    black = set(instance["black"])
    white = set(instance["white"])
    black_liberties = 0
    white_liberties = 0
    for row in range(BOARD_SIZE):
        for column in range(BOARD_SIZE):
            point = (row, column)
            if point in black or point in white:
                continue
            neighbors = {
                (row + row_delta, column + column_delta)
                for row_delta, column_delta in DIRECTIONS
                if 0 <= row + row_delta < BOARD_SIZE
                and 0 <= column + column_delta < BOARD_SIZE
            }
            black_liberties += bool(neighbors & black)
            white_liberties += bool(neighbors & white)
    return black_liberties, white_liberties


def _format_stones(stones: list[tuple[int, int]]) -> str:
    return " ".join(f"{row} {column}" for row, column in stones)


def _case(
    name: str,
    black: list[tuple[int, int]],
    white: list[tuple[int, int]],
) -> dict[str, Any]:
    instance = {"black": black, "white": white}
    black_liberties, white_liberties = empty_point_oracle(instance)
    return {
        "name": name,
        "instance": instance,
        "input": f"{_format_stones(black)}\n{_format_stones(white)}",
        "output": f"{black_liberties} {white_liberties}",
    }


def build_p00279_cases(seed: int, random_count: int) -> list[dict[str, Any]]:
    all_points = [(row, column) for row in range(BOARD_SIZE) for column in range(BOARD_SIZE)]
    black_full = [point for point in all_points if (point[0] + point[1]) % 2 == 0]
    white_full = [point for point in all_points if (point[0] + point[1]) % 2 == 1]
    cases = [
        _case(
            "sample",
            [(0, 5), (8, 9), (9, 10)],
            [(5, 0), (9, 9), (9, 8)],
        ),
        _case("opposite-corners", [(0, 0)], [(18, 18)]),
        _case("center-stones", [(9, 9)], [(3, 3)]),
        _case("shared-liberty", [(0, 0), (0, 2)], [(18, 18)]),
        _case("opponent-blocks-liberty", [(9, 9)], [(9, 10)]),
        _case("empty-point-counts-for-both", [(8, 9), (10, 9)], [(9, 8), (9, 10)]),
        _case("edge-strips", [(0, 0), (0, 1), (0, 2)], [(18, 16), (18, 17), (18, 18)]),
        _case("eye-counts", [(8, 9), (9, 8), (9, 10), (10, 9)], [(0, 0)]),
        _case("surrounded-stones", [(9, 9)], [(8, 9), (9, 8), (9, 10), (10, 9)]),
        _case("full-board", black_full, white_full),
    ]

    generator = random.Random(seed)
    for index in range(random_count):
        shuffled = all_points.copy()
        generator.shuffle(shuffled)
        black_count = generator.randint(1, 90)
        white_count = generator.randint(1, 90)
        cases.append(
            _case(
                f"random-{index:03d}",
                shuffled[:black_count],
                shuffled[black_count : black_count + white_count],
            )
        )
    return cases


def verify_p00279(seed: int, random_count: int) -> dict[str, Any]:
    cases = build_p00279_cases(seed, random_count)
    return differential_verify(
        reference=liberty_sets_reference,
        oracle=empty_point_oracle,
        case_factory=lambda _random: [case["instance"] for case in cases],
        seed=seed,
    )


def build_p00279_problem(authorization_ref: str, seed: int, random_count: int) -> dict[str, Any]:
    cases = build_p00279_cases(seed, random_count)
    verification = verify_p00279(seed, random_count)
    verification["reportSha256"] = content_digest(verification)
    return {
        "schemaVersion": 1,
        "sourceSystem": "manual",
        "sourceDomain": "user-provided",
        "sourceId": "P00279",
        "sourceUrl": "",
        "authorizationRef": authorization_ref,
        "title": "围棋的气",
        "description": (
            "在 19×19 围棋棋盘上，给定黑棋和白棋的坐标。某颜色的气是与该颜色至少一枚棋子上下左右相邻、"
            "且没有棋子的交点总数；同一空交点被多枚同色棋子共享时只计算一次，眼也按气计算。"
        ),
        "inputFormat": (
            "输入共两行。第一行是黑棋坐标，第二行是白棋坐标。每行包含偶数个以空格分隔的整数，"
            "每两个整数依次表示行号和列号，范围均为 0 到 18。"
        ),
        "outputFormat": "输出两个以空格分隔的整数，依次表示黑棋和白棋的气数。",
        "sampleInput": "0 5 8 9 9 10\n5 0 9 9 9 8",
        "sampleOutput": "8 7",
        "hint": "只考虑上下左右相邻交点；同一空交点对每种颜色最多贡献一口气。",
        "timeLimitMs": 1000,
        "memoryLimitKb": 262144,
        "judgeMode": "default",
        "tags": ["模拟", "集合", "围棋"],
        "status": "DRAFT",
        "workflowState": "human-approved",
        "verification": verification,
        "testCases": [{"input": case["input"], "output": case["output"]} for case in cases],
    }
