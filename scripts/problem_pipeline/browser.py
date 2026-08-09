import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .hydro import validate_source_id


class BrowserFetchError(RuntimeError):
    pass


def build_browser_command(
    script_path: Path,
    playwright_module_path: Path,
    browser_executable_path: Path,
    source_id: str,
) -> list[str]:
    return [
        "node",
        str(script_path.resolve()),
        "--playwright",
        str(playwright_module_path.resolve()),
        "--browser",
        str(browser_executable_path.resolve()),
        source_id,
    ]


def fetch_problem_page(
    source_id: str,
    script_path: Path,
    playwright_module_path: Path,
    browser_executable_path: Path,
    run: Callable[..., Any] = subprocess.run,
) -> tuple[int, str]:
    validate_source_id(source_id)
    command = build_browser_command(
        script_path,
        playwright_module_path,
        browser_executable_path,
        source_id,
    )
    result = run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=2100,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "browser fetch failed"
        raise BrowserFetchError(detail)
    try:
        payload = json.loads(result.stdout)
        status = payload["status"]
        html = payload["html"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise BrowserFetchError("browser returned malformed output") from error
    if not isinstance(status, int) or not isinstance(html, str):
        raise BrowserFetchError("browser returned invalid page fields")
    return status, html
