"""Короткие тексты для Bitrix24 — без технических деталей."""

from __future__ import annotations

import re

from qa_release_bot.markdown_report import AnalystReport
from qa_release_bot.summary_report import SummaryReport


def release_verdict_short(decision_verdict: str) -> str:
    if decision_verdict == "forbidden":
        return "ЗАПРЕЩЁН"
    if decision_verdict == "risk":
        return "С РИСКОМ"
    return "ОК"


def format_release_notify(project_id: str, report: AnalystReport, report_url: str) -> str:
    verdict = release_verdict_short(report.decision.verdict)
    lines = [
        f"🚦 Релиз {project_id} — {verdict}",
        f"🔴 Блокеры: {len(report.blockers)}  🟠 High: {len(report.highs)}",
    ]
    if report_url:
        lines.append(f"👉 Отчёт: {report_url}")
    return "\n".join(lines)


def format_summary_notify(
    project_id: str,
    summary: SummaryReport,
    *,
    disappeared_count: int,
    report_url: str,
) -> str:
    new_n = len(summary.new_issues)
    lines = [
        f"📊 Сводка {project_id} — готова",
        f"🆕 Новых ошибок: {new_n}  ✅ Исчезло: {disappeared_count}",
    ]
    if report_url:
        lines.append(f"👉 Отчёт: {report_url}")
    return "\n".join(lines)


def format_failure_notify(project_id: str, command: str, error: str) -> str:
    short = _first_line(error)
    return f"❌ Ошибка: {command} {project_id}\n{short}"


def _first_line(text: str, max_len: int = 200) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "см. лог Actions"
    line = re.sub(r"\s+", " ", line)
    if len(line) > max_len:
        return line[: max_len - 1] + "…"
    return line
