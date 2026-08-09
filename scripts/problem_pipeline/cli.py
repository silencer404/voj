import argparse
import json
from pathlib import Path
from functools import partial

from .browser import fetch_problem_page
from .collector import (
    DEFAULT_INTERVAL_SECONDS,
    collect_authorized_pages,
    validate_browser_environment,
)
from .hydro import CollectionState, expand_source_range, validate_source_id
from .manual import prepare_manual_problem
from .planning import build_import_plan
from .problem_mapping import load_problem_mapping
from .public_content import write_public_content
from .segmentation import write_validated_problem


def _load_problems(directory: Path) -> list[dict]:
    paths = sorted(set(directory.glob("*.json")) | set(directory.glob("*/problem.json")))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voj-problem-pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--problems", required=True, type=Path)
    source = plan.add_mutually_exclusive_group(required=True)
    source.add_argument("--range")
    source.add_argument("--source-id")
    plan.add_argument("--authorization-ref", required=True)
    plan.add_argument("--mapping", required=True, type=Path)
    plan.add_argument("--output", required=True, type=Path)
    collect = commands.add_parser("collect")
    collect.add_argument("--workspace", required=True, type=Path)
    collect.add_argument("--range", required=True)
    collect.add_argument("--authorization-ref", required=True)
    collect.add_argument("--playwright", required=True)
    collect.add_argument("--browser", required=True)
    collect.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    collect.add_argument("--max-pages", type=int, default=1)
    manual = commands.add_parser("prepare-manual")
    manual.add_argument("--workspace", required=True, type=Path)
    manual.add_argument("--source-id", required=True)
    manual.add_argument("--authorization-ref", required=True)
    manual.add_argument("--title-file", required=True, type=Path)
    manual.add_argument("--statement-file", required=True, type=Path)
    validate = commands.add_parser("validate")
    validate.add_argument("--workspace", required=True, type=Path)
    validate.add_argument("--source-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "plan":
        problems = _load_problems(args.problems)
        if args.range:
            source_ids = expand_source_range(args.range)
        else:
            source_ids = [args.source_id]
            matching = [problem for problem in problems if problem.get("sourceId") == args.source_id]
            if len(matching) != 1 or matching[0].get("sourceSystem") != "manual":
                raise ValueError("--source-id is only valid for one manual problem")
        mapping = load_problem_mapping(args.mapping)
        plan = build_import_plan(problems, source_ids, args.authorization_ref, mapping)
        _write_json(args.output, plan)
        return 2 if plan["rejectedCount"] else 0
    if args.command == "collect":
        playwright_path, browser_path = validate_browser_environment(
            args.playwright, args.browser
        )
        script_path = Path(__file__).with_name("fetch_hydro_page.mjs")
        report = collect_authorized_pages(
            workspace=args.workspace,
            source_ids=expand_source_range(args.range),
            authorization_ref=args.authorization_ref,
            fetch_page=partial(
                fetch_problem_page,
                script_path=script_path,
                playwright_module_path=playwright_path,
                browser_executable_path=browser_path,
            ),
            interval_seconds=args.interval_seconds,
            max_pages=args.max_pages,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "prepare-manual":
        validate_source_id(args.source_id)
        public_content = prepare_manual_problem(
            args.source_id,
            args.authorization_ref,
            args.title_file,
            args.statement_file,
        )
        problem_directory = args.workspace.resolve() / "problems" / args.source_id
        write_public_content(problem_directory / "public-content.json", public_content)
        print(
            json.dumps(
                {
                    "sourceId": args.source_id,
                    "publicContentSha256": public_content["publicContentSha256"],
                    "status": "public-content-ready",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "validate":
        validate_source_id(args.source_id)
        problem_directory = args.workspace.resolve() / "problems" / args.source_id
        validation = write_validated_problem(problem_directory)
        state_path = args.workspace.resolve() / "collection-state.json"
        if state_path.exists():
            state = CollectionState.load(state_path, [args.source_id])
            state.record_normalized(args.source_id)
            state.save()
        print(json.dumps(validation, ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError("unknown command")


if __name__ == "__main__":
    raise SystemExit(main())
