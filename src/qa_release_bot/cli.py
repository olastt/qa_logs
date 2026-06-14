from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from qa_release_bot.bot import QAReleaseBot
from qa_release_bot.config import Settings, build_project_refs, load_report_config, report_output_dir
from qa_release_bot.logging_setup import configure_logging
from qa_release_bot.new_issue_watch import format_new_issue_watch_notify, watch_new_issues
from qa_release_bot.projects import ALL_PROJECTS_LABEL, list_cli_projects
from qa_release_bot.run_facade import (
    append_ci_message,
    notify_with_url,
    run_release,
    run_summary,
)


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--html",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Сохранить HTML-отчёт (по умолчанию включено)",
    )
    parser.add_argument(
        "--no-stack",
        action="store_true",
        help="Не загружать стек-трейсы (быстрее)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Отправить результат в Bitrix24 (нужны BITRIX_* в окружении)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Логи API в stderr")


def _run_for_projects(
    command: str,
    project_ids: list[str],
    settings: Settings,
    *,
    save_html: bool,
    no_stack: bool,
) -> int:
    messages: list[str] = []
    exit_code = 0
    cfg = load_report_config()
    out_dir = Path(report_output_dir(cfg))

    for pid in project_ids:
        try:
            if command == "release":
                result = run_release(
                    pid,
                    settings,
                    save_html=save_html,
                    no_stack=no_stack,
                    print_console=len(project_ids) == 1,
                )
            else:
                result = run_summary(
                    pid,
                    settings,
                    save_html=save_html,
                    no_stack=no_stack,
                    print_console=len(project_ids) == 1,
                )
            messages.append(result.notify_text)
            print(result.notify_text)
        except Exception as exc:
            exit_code = 1
            msg = f"❌ Ошибка: {command} {pid}\n{exc}"
            messages.append(msg)
            print(msg, file=sys.stderr)

    if messages:
        append_ci_message(out_dir, messages)
    return exit_code


def _maybe_bitrix(messages: list[str], report_url: str = "") -> None:
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if scripts_dir.is_dir() and str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from bitrix_notify import send_message
    except ImportError:
        return
    text = "\n\n".join(messages)
    if report_url:
        text = notify_with_url(text, report_url)
    send_message(text)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="qa-bot",
        description="QA Bot — проверка релиза и сводки по Glitchtip",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    release_p = sub.add_parser("release", help="Проверка готовности релиза (test + stage)")
    release_p.add_argument("project", help="ID проекта или «ВСЕ ПРОЕКТЫ»")
    _add_common_flags(release_p)

    summary_p = sub.add_parser("summary", help="Сводка: что нового с прошлого запуска")
    summary_p.add_argument("project", help="ID проекта или «ВСЕ ПРОЕКТЫ»")
    _add_common_flags(summary_p)

    new_issues_p = sub.add_parser(
        "new-issues",
        help="Check summary projects for absolutely new Glitchtip issues",
    )
    new_issues_p.add_argument("project", help="Project ID, comma-separated IDs, or ALL")
    new_issues_p.add_argument("--state-db", type=Path, default=None)
    new_issues_p.add_argument("--notify", action="store_true")
    new_issues_p.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("projects", help="Список доступных проектов")

    # Скрытые команды для совместимости
    legacy = sub.add_parser("report", help=argparse.SUPPRESS)
    legacy.add_argument("--legacy", action="store_true")
    legacy.add_argument("-v", "--verbose", action="store_true")
    legacy.add_argument("--no-stack", action="store_true")

    sub.add_parser("run-once", help=argparse.SUPPRESS)
    sub.add_parser("list-projects", help=argparse.SUPPRESS)
    poll = sub.add_parser("poll", help=argparse.SUPPRESS)
    poll.add_argument("--interval", type=int, default=None)

    args = parser.parse_args()
    configure_logging(verbose=getattr(args, "verbose", False))
    settings = Settings()

    if args.command == "projects":
        from qa_release_bot.config import _cli_alias_maps, load_report_config

        cfg = load_report_config()
        summary_aliases, release_aliases = _cli_alias_maps(cfg)

        def _instance(p) -> str:
            key = p.comparison_name or p.summary_config_name or p.id
            if key.startswith("selectel-"):
                return "selectel"
            if key.startswith("hetzner-"):
                return "hetzner"
            return "—"

        for inst in ("selectel", "hetzner"):
            print(f"\n[{inst.upper()}]")
            for kind, label in (("release", "Релиз (test ↔ stage/production)"), ("summary", "Сводка")):
                items = [p for p in list_cli_projects() if p.kind == kind and _instance(p) == inst]
                if not items:
                    continue
                print(f"  {label}:")
                for p in sorted(items, key=lambda x: x.id):
                    print(f"    {p.id}")
        other_release = [p for p in list_cli_projects() if p.kind == "release" and _instance(p) == "—"]
        if other_release:
            print("\n[РЕЛИЗ]")
            for p in other_release:
                print(f"  {p.id}")
        if summary_aliases or release_aliases:
            print("\n[алиасы]")
            for short, full in sorted(release_aliases.items()):
                print(f"  {short} → {full}")
            for short, full in sorted(summary_aliases.items()):
                print(f"  {short} → {full}")
        return

    if args.command in ("release", "summary"):
        raw = args.project.strip()
        if raw.upper() in (ALL_PROJECTS_LABEL, "ALL", "*"):
            ids = [p.id for p in list_cli_projects() if p.kind == args.command]
        else:
            ids = [raw]

        code = _run_for_projects(
            args.command,
            ids,
            settings,
            save_html=args.html,
            no_stack=args.no_stack,
        )
        if args.notify:
            out_dir = Path(report_output_dir(load_report_config()))
            msg = out_dir / "ci_message.txt"
            if msg.is_file():
                _maybe_bitrix([msg.read_text(encoding="utf-8")])
        sys.exit(code)

    if args.command == "new-issues":
        raw = args.project.strip()
        if raw.upper() in (ALL_PROJECTS_LABEL, "ALL", "*"):
            ids = [p.id for p in list_cli_projects() if p.kind == "summary"]
        else:
            ids = [p.strip() for p in raw.split(",") if p.strip()]
        result = watch_new_issues(settings, ids, state_db_path=args.state_db)
        text = format_new_issue_watch_notify(result)
        print(text)
        if args.notify and result.alerts:
            _maybe_bitrix([text])
        return

    if args.command == "report":
        from datetime import datetime, timezone

        from qa_release_bot.qa_analyst_runner import QAAnalystRunner
        from qa_release_bot.qa_report import QAReportRunner

        if getattr(args, "legacy", False):
            QAReportRunner(settings).run_and_export()
            return
        report_cfg = load_report_config()
        out_dir = Path(report_output_dir(report_cfg))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        md_path = out_dir / f"qa-release-{stamp}.md"
        QAAnalystRunner(settings).run(
            save_markdown=md_path,
            save_html=True,
            enrich_stack=False if getattr(args, "no_stack", False) else None,
        )
        return

    if args.command == "list-projects":
        for ref in build_project_refs(settings):
            print(f"[{ref.instance}] {ref.display_name} ({ref.slug})")
        return

    bot = QAReleaseBot(settings)
    if args.command == "run-once":
        bot.run_once()
        return
    if args.command == "poll":
        interval = args.interval or settings.poll_interval_sec
        while True:
            bot.run_once()
            time.sleep(interval)


if __name__ == "__main__":
    main()
