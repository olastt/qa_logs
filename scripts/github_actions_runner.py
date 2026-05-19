#!/usr/bin/env python3
"""Запуск qa-bot в GitHub Actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qa_release_bot.config import Settings, load_report_config, report_output_dir  # noqa: E402
from qa_release_bot.notify_format import format_failure_notify  # noqa: E402
from qa_release_bot.projects import ALL_PROJECTS_LABEL, list_cli_projects  # noqa: E402
from qa_release_bot.run_facade import (  # noqa: E402
    append_ci_message,
    notify_with_url,
    run_release,
    run_summary,
)


def _projects_for_command(command: str) -> list[str]:
    return [p.id for p in list_cli_projects() if p.kind == command]


def _run_one(command: str, project_id: str, *, no_stack: bool) -> str:
    settings = Settings()
    if command == "release":
        result = run_release(
            project_id,
            settings,
            save_html=True,
            no_stack=no_stack,
            print_console=False,
        )
    else:
        result = run_summary(
            project_id,
            settings,
            save_html=True,
            no_stack=no_stack,
            print_console=False,
        )
    return result.notify_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["release", "summary"])
    parser.add_argument("project", help="ID проекта или «ВСЕ ПРОЕКТЫ»")
    parser.add_argument("--no-stack", action="store_true", default=True)
    args = parser.parse_args()

    cfg = load_report_config()
    out_dir = Path(report_output_dir(cfg))
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.project.strip().upper() in (ALL_PROJECTS_LABEL, "ALL", "*"):
        project_ids = _projects_for_command(args.command)
    else:
        project_ids = [args.project.strip()]

    messages: list[str] = []
    failed = False
    for pid in project_ids:
        try:
            text = _run_one(args.command, pid, no_stack=args.no_stack)
            messages.append(text)
            print(text)
        except Exception as exc:
            failed = True
            text = format_failure_notify(pid, args.command, str(exc))
            messages.append(text)
            print(text, file=sys.stderr)

    append_ci_message(out_dir, messages)

    # Список доменов Surge для workflow
    surge_jobs: list[dict[str, str]] = []
    for pid in project_ids:
        meta_path = out_dir / f"ci_meta_{pid}.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            surge_jobs.append(
                {
                    "project_id": pid,
                    "domain": str(meta.get("surge_domain", "")),
                    "html_path": str(meta.get("html_path", "")),
                }
            )
    (out_dir / "ci_surge.json").write_text(
        json.dumps(surge_jobs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
