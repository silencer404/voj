import heapq
import random
from typing import Any

from .verification import differential_verify


def dijkstra_reference(instance: dict[str, Any]) -> int:
    node_count = instance["n"]
    source = instance["source"]
    graph: list[list[tuple[int, int]]] = [[] for _ in range(node_count + 1)]
    for start, end, weight in instance["edges"]:
        graph[start].append((end, weight))
    infinity = 10**30
    distance = [infinity] * (node_count + 1)
    distance[source] = 0
    queue = [(0, source)]
    while queue:
        elapsed, node = heapq.heappop(queue)
        if elapsed != distance[node]:
            continue
        for neighbor, weight in graph[node]:
            candidate = elapsed + weight
            if candidate < distance[neighbor]:
                distance[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    answer = max(distance[1:])
    return -1 if answer == infinity else answer


def bellman_ford_oracle(instance: dict[str, Any]) -> int:
    node_count = instance["n"]
    infinity = 10**30
    distance = [infinity] * (node_count + 1)
    distance[instance["source"]] = 0
    for _ in range(node_count - 1):
        changed = False
        for start, end, weight in instance["edges"]:
            if distance[start] != infinity and distance[start] + weight < distance[end]:
                distance[end] = distance[start] + weight
                changed = True
        if not changed:
            break
    if any(value == infinity for value in distance[1:]):
        return -1
    return max(distance[1:])


def _format_input(instance: dict[str, Any]) -> str:
    lines = [str(instance["n"]), str(len(instance["edges"]))]
    lines.extend(" ".join(map(str, edge)) for edge in instance["edges"])
    lines.append(str(instance["source"]))
    return "\n".join(lines)


def _case(name: str, instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "instance": instance,
        "input": _format_input(instance),
        "output": str(bellman_ford_oracle(instance)),
    }


def build_p00278_cases(seed: int, random_count: int) -> list[dict[str, Any]]:
    cases = [
        _case(
            "sample",
            {"n": 4, "edges": [(2, 1, 1), (2, 3, 1), (3, 4, 1)], "source": 2},
        ),
        _case("single-node", {"n": 1, "edges": [], "source": 1}),
        _case("unreachable", {"n": 3, "edges": [(1, 2, 4)], "source": 1}),
        _case("directed-edge", {"n": 2, "edges": [(2, 1, 7)], "source": 1}),
        _case(
            "faster-indirect-path",
            {"n": 4, "edges": [(1, 2, 10), (1, 3, 2), (3, 2, 2), (2, 4, 1)], "source": 1},
        ),
        _case(
            "max-node-chain",
            {"n": 200, "edges": [(node, node + 1, 1) for node in range(1, 200)], "source": 1},
        ),
        _case(
            "duplicate-directed-edge",
            {"n": 3, "edges": [(1, 2, 9), (1, 2, 2), (2, 3, 4)], "source": 1},
        ),
        _case(
            "zero-weight-cycle",
            {"n": 3, "edges": [(1, 2, 0), (2, 1, 0), (2, 3, 5)], "source": 1},
        ),
    ]
    generator = random.Random(seed)
    for index in range(random_count):
        node_count = generator.randint(1, 12)
        edges: list[tuple[int, int, int]] = []
        for start in range(1, node_count + 1):
            for end in range(1, node_count + 1):
                if start != end and generator.random() < 0.22:
                    edges.append((start, end, generator.randint(0, 30)))
        instance = {
            "n": node_count,
            "edges": edges,
            "source": generator.randint(1, node_count),
        }
        cases.append(_case(f"random-{index:03d}", instance))
    return cases


def verify_p00278(seed: int, random_count: int) -> dict[str, Any]:
    cases = build_p00278_cases(seed, random_count)
    return differential_verify(
        reference=dijkstra_reference,
        oracle=bellman_ford_oracle,
        case_factory=lambda _random: [case["instance"] for case in cases],
        seed=seed,
    )
