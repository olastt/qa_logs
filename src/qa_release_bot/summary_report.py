from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from qa_release_bot.issue_analysis import analyze_issue_full, format_analysis_block
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issues import NewIssueItem
from qa_release_bot.noise_groups import GroupedNoise
from qa_release_bot.glitchtip_levels import level_display, total_in_sections
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
    product_issue_count: int = 0
    noise_excluded_count: int = 0
    before_title_dedupe_count: int = 0
    api_fetch_limit: int = 100
    project_id: str = ""
    level_sections: list[tuple[str, list[IssueRecord]]] = field(default_factory=list)
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
        "## 🆕 Новые логи за сегодня",
    ]
    lines.extend(_render_new_issues(report))
    lines.append("")
    lines.extend(_render_totals(report))
    lines.append("")
    lines.extend(_render_decision(report))
    lines.append("")
    lines.extend(_render_level_sections(report))
    if report.noise_groups:
        lines.append("")
        lines.append("## 🗑️ Шум (сгруппировано)")
        for g in report.noise_groups:
            lines.append(f"- {g.label} — **{g.total_count}** повторов ({g.issue_count} issue)")
    lines.append("---")
    return "\n".join(lines)


def _render_new_issues(report: SummaryReport) -> list[str]:
    if not report.new_issues:
        lines = ["✅ **Новых логов за сегодня (МСК) нет.**"]
        if report.is_first_run:
            lines.append("_Снапшот для динамики сохранён._")
        return lines
    lines = [
        f"**Сегодня появилось: {len(report.new_issues)}** (first_seen за текущий день, МСК)",
        "",
    ]
    if report.is_first_run:
        lines.insert(0, "📌 Первый снапшот сохранён — ниже логи, появившиеся сегодня.")
        lines.insert(1, "")
    for item in report.new_issues[:25]:
        analysis = analyze_issue_full(
            item.issue, item.severity, summary_mode=True
        )
        lines.append(f"### {analysis.tracker_title}")
        lines.append(format_analysis_block(analysis, summary_mode=True))
        lines.append(f"- {item.deploy_hint}")
        if analysis.glitchtip_url:
            lines.append(f"- {analysis.glitchtip_url}")
        lines.append("")
    rest = len(report.new_issues) - min(25, len(report.new_issues))
    if rest > 0:
        lines.append(f"_… ещё {rest}_")
    return lines


def _render_totals(report: SummaryReport) -> list[str]:
    product = report.product_issue_count or total_in_sections(report.level_sections)
    merged = max(0, report.before_title_dedupe_count - product)
    cap = ""
    if report.total_unresolved >= report.api_fetch_limit:
        cap = f" (не более **{report.api_fetch_limit}** за один запрос API)"
    level_bits = " · ".join(
        f"**{level_display(level)}** {len(issues)}"
        for level, issues in report.level_sections
        if issues
    )
    return [
        "## 📊 Итого",
        f"- Загружено из Glitchtip (`{report.issue_query}` · {report.stats_period}): "
        f"**{report.total_unresolved}** issue{cap}",
        f"- Вынесено в «Шум» (file_put_contents, ClickHouse): **{report.noise_excluded_count}**",
        f"- После объединения одинаковых title: **{product}** "
        f"({report.before_title_dedupe_count} → {product}, схлопнуто **{merged}**)",
        f"- В плитках и секциях по Level: {level_bits or '—'} (сумма = **{product}**)",
    ]


def _render_level_sections(report: SummaryReport) -> list[str]:
    lines: list[str] = []
    for level, issues in report.level_sections:
        lines.append(f"## {level_display(level)} ({len(issues)})")
        lines.extend(_render_issues(issues))
        lines.append("")
    if not report.level_sections:
        lines.append("_Нет логов в выборке._")
    return lines


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
        analysis = analyze_issue_full(issue, sev, summary_mode=True)
        stale = "\n\n> 🕰️ **STALE** — давно не воспроизводилось\n" if analysis.is_stale else ""
        out.append(f"### {analysis.tracker_title}{stale}")
        out.append(format_analysis_block(analysis, summary_mode=True))
        out.append("")
    return out


