import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .hydro import CollectionState, HydroParseError, extract_public_problem
from .public_content import write_public_content


DEFAULT_INTERVAL_SECONDS = 60


class CollectionHalted(RuntimeError):
    pass


def validate_browser_environment(
    playwright_module_path: str, browser_executable_path: str
) -> tuple[Path, Path]:
    module_path = Path(playwright_module_path).expanduser().resolve()
    browser_path = Path(browser_executable_path).expanduser().resolve()
    if not module_path.is_dir():
        raise FileNotFoundError(f"local Playwright module not found: {module_path}")
    if not browser_path.is_file():
        raise FileNotFoundError(f"local browser executable not found: {browser_path}")
    return module_path, browser_path


def _looks_like_login(html: str) -> bool:
    lowered = html.lower()
    return "<title>login</title>" in lowered or "/accounts/login" in lowered


def collect_authorized_pages(
    workspace: Path,
    source_ids: list[str],
    authorization_ref: str,
    fetch_page: Callable[[str], tuple[int, str]],
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
    max_pages: int | None = None,
) -> dict[str, Any]:
    if not authorization_ref.strip():
        raise ValueError("authorization reference is required")
    if interval_seconds < DEFAULT_INTERVAL_SECONDS:
        raise ValueError(
            f"collection interval cannot be shorter than {DEFAULT_INTERVAL_SECONDS} seconds"
        )

    workspace = workspace.resolve()
    problems_directory = workspace / "problems"
    problems_directory.mkdir(parents=True, exist_ok=True)
    state = CollectionState.load(workspace / "collection-state.json", source_ids)
    pending = state.pending_ids()
    if max_pages is not None:
        pending = pending[:max_pages]

    fetched: list[str] = []
    for source_id in pending:
        current_time = now()
        if state.last_fetched_at is not None:
            remaining = interval_seconds - (current_time - state.last_fetched_at)
            if remaining > 0:
                sleep(remaining)
        status, html = fetch_page(source_id)
        if status in {401, 403, 429}:
            raise CollectionHalted(f"collection halted by HTTP {status} for {source_id}")
        if status != 200:
            raise CollectionHalted(f"unexpected HTTP {status} for {source_id}")
        if _looks_like_login(html):
            raise CollectionHalted(f"collection redirected to login for {source_id}")
        try:
            public_content = extract_public_problem(html, source_id, authorization_ref)
        except HydroParseError as error:
            raise CollectionHalted(
                f"page structure validation failed for {source_id}: {error}"
            ) from error

        problem_directory = problems_directory / source_id
        write_public_content(problem_directory / "public-content.json", public_content)
        state.record_html(source_id, html, status, now())
        state.save()
        fetched.append(source_id)

    return {
        "fetched": fetched,
        "remaining": state.pending_ids(),
        "intervalSeconds": interval_seconds,
    }
