from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from qa_release_bot.issue_analysis import analyze_issue_full, format_analysis_block
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issues import NewIssueItem
from qa_release_bot.noise_groups import GroupedNoise
from qa_release_bot.release_decision import ReleaseDecision
from qa_release_bot.severity_rules import IssueSeverity, classify_severity
from qa_release_bot.tuesday_diff import is_stale


@dataclass(slots=True)
class SummaryReport:
    """Сводка по одному проекту / окружению (без test↔stage)."""

    product_name: str
    instance: str
    project_slug: str
    fetched_at: datetime
    decision: ReleaseDecision
    total_unresolved: int
    blockers: list[IssueRecord] = field(default_factory=list)
    highs: list[IssueRecord] = field(default_factory=list)
    mediums: list[IssueRecord] = field(default_factory=list)
    lows: list[IssueRecord] = field(default_factory=list)
    noise_groups: list[GroupedNoise] = field(default_factory=list)
    new_issues: list[NewIssueItem] = field(default_factory=list)
    disappeared_count: int = 0
    is_first_run: bool = False
    stats_period: str = "14d"
    issue_query: str = "is:unresolved"


def render_summary_markdown(report: SummaryReport) -> str:
    now = report.fetched_at.astimezone(timezone.utc)
    lines: list[str] = [
        "---",
        f"# 📋 Сводка логов — {report.product_name}",
        f"📅 {now.strftime('%Y-%m-%d %H:%M UTC')} | "
        f"`{report.instance}` / `{report.project_slug}`",
        f"🔍 `{report.issue_query}` · период **{report.stats_period}**",
        "",
        "## 🆕 Появилось впервые",
    ]
    lines.extend(_render_new_issues(report))
    lines.append("")
    lines.extend(_render_totals(report))
    lines.append("")
    lines.extend(_render_decision(report))
    lines.append("")
    lines.append(f"## 🔴 Блокеры ({len(report.blockers)})")
    lines.extend(_render_issues(report.blockers))
    lines.append("")
    lines.append(f"## 🟠 High ({len(report.highs)})")
    lines.extend(_render_issues(report.highs))
    lines.append("")
    lines.extend(_render_medium_low(report))
    if report.noise_groups:
        lines.append("")
        lines.append("## 🗑️ Шум (сгруппировано)")
        for g in report.noise_groups:
            lines.append(f"- {g.label} — **{g.total_count}** повторов ({g.issue_count} issue)")
    lines.append("---")
    return "\n".join(lines)


def _render_new_issues(report: SummaryReport) -> list[str]:
    if report.is_first_run:
        return [
            "📌 **Первый запуск.** Снапшот сохранён.",
            "Новые логи появятся в следующей сводке.",
        ]
    if not report.new_issues:
        return ["✅ **Новых логов нет** — всё уже было известно."]
    lines = [f"**🆕 ПОЯВИЛОСЬ ВПЕРВЫЕ ({len(report.new_issues)})**", ""]
    for item in report.new_issues[:25]:
        lines.append("```")
        lines.append(item.tracker_title)
        lines.append(f"Серьёзность: {item.severity.value.upper()}")
        lines.append(f"Первый раз: {item.issue.first_seen} | Повторов: {item.issue.count}")
        lines.append(f"Вероятная причина: {item.deploy_hint}")
        lines.append("```")
        lines.append("")
    rest = len(report.new_issues) - min(25, len(report.new_issues))
    if rest > 0:
        lines.append(f"_… ещё {rest}_")
    return lines


def _render_totals(report: SummaryReport) -> list[str]:
    product = len(report.blockers) + len(report.highs) + len(report.mediums) + len(report.lows)
    return [
        "## 📊 Итого",
        f"- Нерешённых в API: **{report.total_unresolved}**",
        f"- После отсечения шума: **{product}** "
        f"(🔴 {len(report.blockers)} · 🟠 {len(report.highs)} · "
        f"🟡 {len(report.mediums)} · 🟢 {len(report.lows)})",
    ]


def _render_decision(report: SummaryReport) -> list[str]:
    lines = [report.decision.headline.replace("**", ""), ""]
    for item in report.decision.items:
        lines.append(f"- {item}")
    return lines


def _render_issues(issues: list[IssueRecord]) -> list[str]:
    if not issues:
        return ["_Нет._"]
    out: list[str] = []
    for issue in issues:
        sev = classify_severity(issue)
        analysis = analyze_issue_full(issue, sev)
        stale = "\n\n> 🕰️ **STALE** — давно не воспроизводилось\n" if analysis.is_stale else ""
        out.append(f"### {analysis.tracker_title}{stale}")
        out.append(format_analysis_block(analysis))
        out.append("")
    return out


def _render_medium_low(report: SummaryReport) -> list[str]:
    lines = [
        "## 🟡 Medium / 🟢 Low",
        f"_Medium: {len(report.mediums)} | Low: {len(report.lows)} — кратко._",
    ]
    for issue in (report.mediums + report.lows)[:30]:
        sev = classify_severity(issue)
        analysis = analyze_issue_full(issue, sev)
        tag = "🕰️ " if is_stale(issue) else ""
        lines.append(f"- {tag}{analysis.tracker_title} (count={issue.count})")
    rest = len(report.mediums) + len(report.lows) - min(30, len(report.mediums) + len(report.lows))
    if rest > 0:
        lines.append(f"_… ещё {rest}_")
    return lines
