from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from qa_release_bot.issue_analysis import analyze_issue_full, format_analysis_block
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issues import NewIssueItem
from qa_release_bot.noise_groups import GroupedNoise
from qa_release_bot.release_decision import ReleaseDecision
from qa_release_bot.severity_rules import IssueSeverity, classify_severity
from qa_release_bot.trends import TrendItem
from qa_release_bot.tuesday_diff import DiffRow, is_stale


@dataclass(slots=True)
class AnalystReport:
    product_name: str
    fetched_at: datetime
    decision: ReleaseDecision
    blockers: list[IssueRecord] = field(default_factory=list)
    highs: list[IssueRecord] = field(default_factory=list)
    mediums: list[IssueRecord] = field(default_factory=list)
    lows: list[IssueRecord] = field(default_factory=list)
    diff_rows: list[DiffRow] = field(default_factory=list)
    regressions: list[IssueRecord] = field(default_factory=list)
    noise_groups: list[GroupedNoise] = field(default_factory=list)
    trends: list[TrendItem] = field(default_factory=list)
    diff_available: bool = True
    test_unique_count: int = 0
    stage_unique_count: int = 0
    shared_count: int = 0
    new_issues_stage: list[NewIssueItem] = field(default_factory=list)
    new_issues_test: list[NewIssueItem] = field(default_factory=list)
    is_first_run: bool = False
    is_tuesday_diff: bool = True
    stats_period: str = "14d"
    issue_query: str = "is:unresolved"


def render_markdown(report: AnalystReport) -> str:
    now = report.fetched_at.astimezone(timezone.utc)
    lines: list[str] = [
        "---",
        f"# 🐾 QA Release Report — {report.product_name}",
        f"📅 {now.strftime('%Y-%m-%d')} | 🔄 Данные: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## 🆕 Появилось впервые",
    ]
    lines.extend(_render_new_issues(report))
    lines.append("")
    lines.extend(_render_decision(report))
    lines.append("")
    lines.append(f"## 🔴 Блокеры ({len(report.blockers)})")
    lines.extend(_render_issues(report.blockers))
    lines.append("")
    lines.append(f"## 🟠 High ({len(report.highs)})")
    lines.extend(_render_issues(report.highs))
    lines.append("")
    lines.extend(_render_diff(report))
    lines.append("")
    lines.extend(_render_regressions(report))
    if report.noise_groups:
        lines.append("")
        lines.append("## 🗑️ Шум (сгруппировано)")
        for g in report.noise_groups:
            lines.append(f"- {g.label} — **{g.total_count}** повторов")
    lines.append("")
    lines.extend(_render_medium_low(report))
    lines.append("---")
    return "\n".join(lines)


def _render_new_issues(report: AnalystReport) -> list[str]:
    if report.is_first_run:
        return [
            "📌 **Первый запуск.** Снапшот сохранён.",
            "Новые логи появятся в следующем отчёте.",
        ]
    all_new = report.new_issues_stage + report.new_issues_test
    if not all_new:
        return ["✅ **Новых логов нет** — всё уже было известно."]
    lines = [f"**🆕 ПОЯВИЛОСЬ ВПЕРВЫЕ ({len(all_new)})**", ""]
    for item in all_new[:25]:
        lines.append("```")
        lines.append(item.tracker_title)
        lines.append(f"Серьёзность: {item.severity.value.upper()} | env: {item.environment}")
        lines.append(f"Первый раз: {item.issue.first_seen} | Повторов: {item.issue.count}")
        lines.append(f"Вероятная причина: {item.deploy_hint}")
        lines.append("```")
        lines.append("")
    rest = len(all_new) - min(25, len(all_new))
    if rest > 0:
        lines.append(f"_… ещё {rest}_")
    return lines


def _render_decision(report: AnalystReport) -> list[str]:
    lines = ["## 🚦 Решение по релизу", report.decision.headline, ""]
    for item in report.decision.items:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(
        f"TEST: {report.test_unique_count} • STAGE: {report.stage_unique_count} • "
        f"Общих: {report.shared_count}"
    )
    return lines


def _render_issues(issues: list[IssueRecord]) -> list[str]:
    if not issues:
        return ["_Нет._"]
    out: list[str] = []
    for issue in issues:
        sev = classify_severity(issue)
        analysis = analyze_issue_full(issue, sev)
        stale = "\n\n> 🕰️ **STALE** — не учитывается в решении о релизе\n" if analysis.is_stale else ""
        out.append(f"### {analysis.tracker_title}{stale}")
        out.append(format_analysis_block(analysis))
        out.append("")
    return out


def _render_diff(report: AnalystReport) -> list[str]:
    lines = ["## 📊 Дифф с прошлым вторником (STAGE)"]
    if not report.is_tuesday_diff or not report.diff_available:
        lines.append("📌 Дифф появится со следующего вторника (нужен снапшот прошлого вторника).")
        return lines
    if not report.diff_rows:
        lines.append("_Изменений нет._")
        return lines
    lines.append("| Issue | Прошлая неделя | Эта неделя | Δ | Статус |")
    lines.append("|-------|----------------|------------|---|--------|")
    for row in report.diff_rows[:40]:
        prev = str(row.prev_count) if row.prev_count is not None else "—"
        curr = str(row.curr_count) if row.curr_count is not None else "—"
        lines.append(f"| {row.title[:45]} | {prev} | {curr} | {row.delta_pct} | {row.status} |")
    return lines


def _render_regressions(report: AnalystReport) -> list[str]:
    lines = [f"## ⚠️ Регрессии ({len(report.regressions)})"]
    if not report.regressions:
        lines.append("_Нет активных регрессий._")
        return lines
    for issue in report.regressions:
        analysis = analyze_issue_full(issue, classify_severity(issue))
        lines.append(f"- **⚠️ РЕГРЕССИЯ:** {analysis.tracker_title} (count={issue.count})")
    return lines


def _render_medium_low(report: AnalystReport) -> list[str]:
    lines = [
        "## 🟡 Medium / 🟢 Low",
        f"_Medium: {len(report.mediums)} | Low: {len(report.lows)} — кратко._",
    ]
    for issue in (report.mediums + report.lows)[:20]:
        tag = "🕰️ " if is_stale(issue) else ""
        lines.append(f"- {tag}[{issue.level}] {issue.title[:70]} (count={issue.count})")
    return lines
