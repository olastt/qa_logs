from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

from qa_release_bot.bot import QAReleaseBot
from qa_release_bot.config import Settings, build_project_refs, load_report_config, report_output_dir
from qa_release_bot.logging_setup import configure_logging
from qa_release_bot.qa_analyst_runner import QAAnalystRunner
from qa_release_bot.qa_report import QAReportRunner
from qa_release_bot.summary_runner import SingleProjectSummaryRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Release Bot — Glitchtip monitor")
    sub = parser.add_subparsers(dest="command")

    report_parser = sub.add_parser(
        "report",
        help="QA-отчёт аналитика (markdown + снапшоты) — по умолчанию",
    )
    report_parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Сохранить markdown (например reports/qa.md)",
    )
    report_parser.add_argument(
        "--legacy",
        action="store_true",
        help="Старый текстовый/PDF отчёт test vs stage",
    )
    report_parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help="Папка отчётов для --legacy",
    )
    report_parser.add_argument("--no-save", action="store_true", help="Не сохранять файлы")
    report_parser.add_argument("--no-console", action="store_true", help="Только файлы")
    report_parser.add_argument("-v", "--verbose", action="store_true", help="Логи API в stderr")
    report_parser.add_argument(
        "--no-stack",
        action="store_true",
        help="Не запрашивать events/latest (быстрее, меньше 429)",
    )
    report_parser.add_argument("--pdf", action="store_true", help="Дополнительно сохранить PDF")
    report_parser.add_argument("--no-html", action="store_true", help="Не сохранять HTML")

    summary_parser = sub.add_parser(
        "summary",
        help="Сводка по одному проекту (без test↔stage)",
    )
    summary_parser.add_argument(
        "--name",
        metavar="NAME",
        help="Имя из config/report.yaml → summaries",
    )
    summary_parser.add_argument(
        "--instance",
        metavar="INSTANCE",
        help="Инстанс: hetzner | selectel",
    )
    summary_parser.add_argument(
        "--project",
        metavar="SLUG",
        help="Slug проекта в API (напр. webappswidgets-test)",
    )
    summary_parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Сохранить markdown",
    )
    summary_parser.add_argument("--no-save", action="store_true", help="Не сохранять markdown/pdf")
    summary_parser.add_argument("--pdf", action="store_true", help="Дополнительно сохранить PDF")
    summary_parser.add_argument("--no-html", action="store_true", help="Не сохранять HTML")
    summary_parser.add_argument("--no-console", action="store_true", help="Только файл")
    summary_parser.add_argument("-v", "--verbose", action="store_true", help="Логи API в stderr")
    summary_parser.add_argument(
        "--no-stack",
        action="store_true",
        help="Не запрашивать events/latest",
    )

    sub.add_parser("run-once", help="Один цикл опроса")
    sub.add_parser("list-projects", help="Показать проекты из config/instances.yaml")

    poll = sub.add_parser("poll", help="Бесконечный опрос с интервалом из .env")
    poll.add_argument("--interval", type=int, default=None, help="Секунды между циклами")

    args = parser.parse_args()
    command = args.command or "report"
    configure_logging(verbose=getattr(args, "verbose", False))
    settings = Settings()

    if command == "report":
        if getattr(args, "legacy", False):
            QAReportRunner(settings).run_and_export(
                output=getattr(args, "output", None),
                output_dir=getattr(args, "output_dir", None),
                save_files=not getattr(args, "no_save", False),
                print_console=not getattr(args, "no_console", False),
            )
            return

        report_cfg = load_report_config()
        out_dir = Path(getattr(args, "output_dir", None) or report_output_dir(report_cfg))
        if getattr(args, "output", None):
            md_path = Path(args.output)
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
            out_dir.mkdir(parents=True, exist_ok=True)
            md_path = out_dir / f"qa-release-{stamp}.md"

        QAAnalystRunner(settings).run(
            save_markdown=None if getattr(args, "no_save", False) else md_path,
            save_html=not getattr(args, "no_html", False) and not getattr(args, "no_save", False),
            save_pdf=getattr(args, "pdf", False) and not getattr(args, "no_save", False),
            print_console=not getattr(args, "no_console", False),
            enrich_stack=False if getattr(args, "no_stack", False) else None,
        )
        return

    if command == "summary":
        report_cfg = load_report_config()
        out_dir = Path(report_output_dir(report_cfg))
        if getattr(args, "output", None):
            md_path = Path(args.output)
        elif not getattr(args, "no_save", False):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
            out_dir.mkdir(parents=True, exist_ok=True)
            md_path = out_dir / f"summary-{stamp}.md"
        else:
            md_path = None

        SingleProjectSummaryRunner(settings).run(
            name=getattr(args, "name", None),
            instance=getattr(args, "instance", None),
            project_slug=getattr(args, "project", None),
            save_markdown=md_path,
            save_html=not getattr(args, "no_html", False) and not getattr(args, "no_save", False),
            save_pdf=getattr(args, "pdf", False) and not getattr(args, "no_save", False),
            print_console=not getattr(args, "no_console", False),
            enrich_stack=False if getattr(args, "no_stack", False) else None,
        )
        return

    if command == "list-projects":
        for ref in build_project_refs(settings):
            print(f"[{ref.instance}] {ref.display_name} ({ref.slug})")
        return

    bot = QAReleaseBot(settings)

    if command == "run-once":
        bot.run_once()
        return

    if command == "poll":
        interval = args.interval or settings.poll_interval_sec
        while True:
            bot.run_once()
            time.sleep(interval)


if __name__ == "__main__":
    main()
