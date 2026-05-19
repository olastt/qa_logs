#!/usr/bin/env python3
"""Запуск qa-release-bot в CI и формирование текста для Bitrix24."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from qa_release_bot.bot import QAReleaseBot  # noqa: E402
from qa_release_bot.config import (  # noqa: E402
    Settings,
    build_project_refs,
    load_report_config,
    report_output_dir,
)
from qa_release_bot.qa_analyst_runner import QAAnalystRunner  # noqa: E402
from qa_release_bot.summary_runner import SingleProjectSummaryRunner  # noqa: E402


def _latest_html(out_dir: Path, pattern: str) -> str | None:
    files = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None


def _run_report(settings: Settings, *, no_stack: bool) -> str:
    cfg = load_report_config()
    out_dir = Path(report_output_dir(cfg))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    md_path = out_dir / f"qa-release-{stamp}.md"

    report = QAAnalystRunner(settings).run(
        save_markdown=md_path,
        save_html=True,
        save_pdf=False,
        print_console=False,
        enrich_stack=False if no_stack else None,
    )
    html = _latest_html(out_dir, "qa_report_*.html")
    lines = [
        "🐾 QA Release Bot — отчёт vetmanager-extjs (test + stage)",
        f"📅 {report.fetched_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        report.decision.headline.replace("**", ""),
        f"🔴 Blocker: {len(report.blockers)} · 🟠 High: {len(report.highs)} · "
        f"🟡 Medium: {len(report.mediums)} · 🟢 Low: {len(report.lows)}",
        f"🆕 Новые (stage): {len(report.new_issues_stage)} · "
        f"новые (test): {len(report.new_issues_test)}",
    ]
    if report.decision.items:
        lines.append("")
        lines.append("Топ проблем:")
        for item in report.decision.items[:8]:
            lines.append(f"• {item}")
    if html:
        lines.append("")
        lines.append(f"📄 HTML: {html} (артефакт Actions)")
    lines.append(f"📝 Markdown: {md_path.name}")
    return "\n".join(lines)


def _run_summary(settings: Settings, name: str, *, no_stack: bool) -> str:
    cfg = load_report_config()
    out_dir = Path(report_output_dir(cfg))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    md_path = out_dir / f"summary-{stamp}.md"

    summary = SingleProjectSummaryRunner(settings).run(
        name=name,
        save_markdown=md_path,
        save_html=True,
        save_pdf=False,
        print_console=False,
        enrich_stack=False if no_stack else None,
    )
    html = _latest_html(out_dir, f"summary_{summary.project_slug.replace('/', '-')}_*.html")
    if not html:
        html = _latest_html(out_dir, "summary_*.html")

    lines = [
        f"🐾 QA Release Bot — сводка {summary.product_name}",
        f"📍 {summary.instance} / {summary.project_slug}",
        f"📅 {summary.fetched_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        summary.decision.headline.replace("**", ""),
        f"Всего unresolved: {summary.total_unresolved}",
        f"🔴 Blocker: {len(summary.blockers)} · 🟠 High: {len(summary.highs)} · "
        f"🟡 Medium: {len(summary.mediums)} · 🟢 Low: {len(summary.lows)}",
        f"🆕 Новые: {len(summary.new_issues)}",
    ]
    if summary.decision.items:
        lines.append("")
        for item in summary.decision.items[:8]:
            lines.append(f"• {item}")
    if html:
        lines.append("")
        lines.append(f"📄 HTML: {html} (артефакт Actions)")
    return "\n".join(lines)


def _run_once(settings: Settings) -> str:
    bot = QAReleaseBot(settings)
    bot.run_once()
    return "🐾 QA Release Bot — run-once завершён (см. логи Actions)"


def _list_projects(settings: Settings) -> str:
    lines = ["🐾 QA Release Bot — проекты:"]
    for ref in build_project_refs(settings):
        lines.append(f"• [{ref.instance}] {ref.display_name} ({ref.slug})")
    return "\n".join(lines) if len(lines) > 1 else "Проекты не найдены (проверьте токены в Secrets)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--command",
        required=True,
        choices=["report", "summary", "run-once", "list-projects"],
    )
    parser.add_argument(
        "--summary-name",
        default="webapps-widgets-test",
        help="name из config/report.yaml → summaries",
    )
    parser.add_argument("--no-stack", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    try:
        if args.command == "report":
            message = _run_report(settings, no_stack=args.no_stack)
        elif args.command == "summary":
            message = _run_summary(settings, args.summary_name, no_stack=args.no_stack)
        elif args.command == "run-once":
            message = _run_once(settings)
        else:
            message = _list_projects(settings)
    except Exception as exc:
        message = f"❌ QA Release Bot — ошибка ({args.command}):\n{exc}"
        print(message, file=sys.stderr)
        if args.notify:
            from bitrix_notify import send_message

            send_message(message)
        raise

    print(message)
    summary_file = ROOT / "reports" / "ci_message.txt"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(message, encoding="utf-8")

    if args.notify:
        from bitrix_notify import send_message

        send_message(message)


if __name__ == "__main__":
    main()
