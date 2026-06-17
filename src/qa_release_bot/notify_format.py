"""Короткие тексты для Bitrix24 — без технических деталей."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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


def format_daily_digest(items: list[dict[str, Any]]) -> str:
    summary_items = [item for item in items if item.get("command") == "summary"]
    total_new = sum(int(item.get("new_issues") or 0) for item in summary_items)
    total_critical = sum(int(item.get("new_critical") or 0) for item in summary_items)
    total_disappeared = sum(int(item.get("disappeared") or 0) for item in summary_items)
    attention = [
        item
        for item in summary_items
        if int(item.get("new_issues") or 0) > 0 or int(item.get("new_critical") or 0) > 0
    ]
    quiet = [item for item in summary_items if int(item.get("new_issues") or 0) == 0]

    lines = [
        "📊 QA daily digest",
        f"Проверено проектов: {len(summary_items)}",
        f"Новых ошибок сегодня: {total_new}",
        f"Критичных новых: {total_critical}",
        f"Исчезло из сводок: {total_disappeared}",
    ]

    if attention:
        lines.append("")
        lines.append("🔴 Требует внимания:")
        for item in sorted(
            attention,
            key=lambda x: (int(x.get("new_critical") or 0), int(x.get("new_issues") or 0)),
            reverse=True,
        ):
            project_id = str(item.get("project_id") or "unknown")
            project_name = str(item.get("project_display_name") or project_id)
            new_n = int(item.get("new_issues") or 0)
            critical_n = int(item.get("new_critical") or 0)
            lines.append(f"- {project_name}: новых {new_n}, критичных {critical_n}")
            for title in (item.get("top_new_titles") or [])[:2]:
                lines.append(f"  • {_first_line(str(title), 120)}")
            url = str(item.get("report_url") or "")
            if url:
                lines.append(f"  Отчёт: {url}")
    else:
        lines.append("")
        lines.append("✅ Новых ошибок по проектам нет.")

    if quiet:
        lines.append("")
        lines.append("✅ Без новых ошибок:")
        for item in quiet[:12]:
            lines.append(f"- {item.get('project_display_name') or item.get('project_id')}")
        if len(quiet) > 12:
            lines.append(f"- ...и ещё {len(quiet) - 12}")

    lines.append("")
    lines.append("🔗 Все отчёты:")
    for item in summary_items:
        project_id = str(item.get("project_id") or "unknown")
        project_name = str(item.get("project_display_name") or project_id)
        url = str(item.get("report_url") or "")
        lines.append(f"- {project_name}: {url or 'отчёт не опубликован'}")

    return "\n".join(lines)


def _first_line(text: str, max_len: int = 200) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "см. лог Actions"
    line = re.sub(r"\s+", " ", line)
    if len(line) > max_len:
        return line[: max_len - 1] + "…"
    return line
