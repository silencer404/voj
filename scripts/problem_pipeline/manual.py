import re
from pathlib import Path
from typing import Any

from .hydro import validate_source_id
from .public_content import build_manual_public_content


def prepare_manual_problem(
    source_id: str,
    authorization_ref: str,
    title_path: Path,
    statement_path: Path,
) -> dict[str, Any]:
    validate_source_id(source_id)
    return build_manual_public_content(
        source_id,
        authorization_ref,
        title_path,
        statement_path,
    )


def normalize_manual_problem(
    source_id: str,
    title: str,
    statement: str,
    authorization_ref: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"P\d{5}", source_id):
        raise ValueError("manual source id must use P00000 format")
    if not title.strip() or not statement.strip() or not authorization_ref.strip():
        raise ValueError("manual problem metadata is incomplete")

    sample = re.search(
        r"示例\s*1?\s*[：:]?\s*\n\s*输入\s*\n(.*?)\n\s*输出\s*\n\s*(-?\d+)",
        statement,
        flags=re.DOTALL,
    )
    if not sample:
        raise ValueError("manual statement sample is missing")
    sample_input = "\n".join(
        line.strip() for line in sample.group(1).strip().splitlines() if line.strip()
    )

    return {
        "schemaVersion": 1,
        "sourceSystem": "manual",
        "sourceDomain": "user-provided",
        "sourceId": source_id,
        "sourceUrl": "",
        "authorizationRef": authorization_ref,
        "title": title.strip(),
        "description": (
            "给定一个包含 N 台电脑的有向网络。病毒从指定电脑开始传播，边 i -> j "
            "的传播耗时为 t。求感染全部电脑所需的最短时间；若存在无法感染的电脑，输出 -1。\n\n"
            "编号范围以输入约束为准，使用 1 到 N。"
        ),
        "inputFormat": (
            "第一行是电脑数量 N；第二行是有向连接数量 M；接下来 M 行每行包含 i、j、t，"
            "表示从 i 到 j 的感染时间；最后一行是最初感染的电脑编号。"
        ),
        "outputFormat": "输出感染全部电脑所需的最短时间；若有电脑不可达，输出 -1。",
        "sampleInput": sample_input,
        "sampleOutput": sample.group(2),
        "hint": "所有连接均为有向边，传播时间为非负整数。",
        "timeLimitMs": 1000,
        "memoryLimitKb": 262144,
        "judgeMode": "default",
        "tags": ["图论", "最短路", "Dijkstra"],
        "status": "DRAFT",
        "workflowState": "parsed",
    }
