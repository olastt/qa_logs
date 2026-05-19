from __future__ import annotations

from dataclasses import dataclass

from qa_release_bot.issue_explain import explain_dev_notes, explain_what_happened
from qa_release_bot.issue_history import IssueHistory, build_issue_history, format_history
from qa_release_bot.issue_history import format_history_span
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.issue_titles import (
    IssueTitleRegistry,
    generate_tracker_title,
    glitchtip_issue_url,
)
from qa_release_bot.module_map import ModuleResolution, load_module_map, resolve_module
from qa_release_bot.severity_rules import IssueSeverity
from qa_release_bot.tuesday_diff import is_stale


@dataclass(slots=True)
class IssueAnalysisFull:
    what_happened: str
    module: str | None
    user_visible: str
    real_danger: str
    risk_label: str
    risk_css: str
    dev_questions: list[str]
    dev_hypothesis: str | None
    tracker_title: str
    history: IssueHistory
    is_stale: bool
    glitchtip_url: str
    group_tag: str
    controller_key: str | None
    is_unmapped_controller: bool


def analyze_issue_full(
    issue: IssueRecord,
    severity: IssueSeverity,
    *,
    registry: IssueTitleRegistry | None = None,
    glitchtip_base_url: str = "",
    glitchtip_org_slug: str = "",
    glitchtip_project_id: str = "",
    module_map: dict[str, str] | None = None,
) -> IssueAnalysisFull:
    reg = registry or IssueTitleRegistry()
    mapping = module_map or load_module_map()
    resolution = resolve_module(issue, mapping)
    title_lower = issue.title.lower()

    module_display = resolution.human_module
    what, is_clear = explain_what_happened(issue)
    user_visible = _user_visible_one_of(title_lower, issue)
    risk_label, risk_css = _risk_label(title_lower, issue, severity)
    danger = risk_label
    questions, hypothesis = explain_dev_notes(issue, what, is_clear=is_clear)
    tracker = generate_tracker_title(issue, resolution, reg)
    history = build_issue_history(issue)

    return IssueAnalysisFull(
        what_happened=what,
        module=module_display,
        user_visible=user_visible,
        real_danger=danger,
        risk_label=risk_label,
        risk_css=risk_css,
        dev_questions=questions,
        dev_hypothesis=hypothesis,
        tracker_title=tracker,
        history=history,
        is_stale=is_stale(issue),
        glitchtip_url=glitchtip_issue_url(
            glitchtip_base_url,
            issue.id,
            issue.org_slug or glitchtip_org_slug,
            issue.project_id or glitchtip_project_id,
        ),
        group_tag=resolution.short_tag,
        controller_key=resolution.controller_key,
        is_unmapped_controller=bool(resolution.controller_key and not resolution.is_mapped),
    )


def format_analysis_block(analysis: IssueAnalysisFull) -> str:
    lines = [f"🔍 **ЧТО СЛУЧИЛОСЬ**\n{analysis.what_happened}"]
    if analysis.module:
        lines.append(f"📍 **МОДУЛЬ**\n{analysis.module}")
    lines.append(f"💥 **ЧТО ВИДИТ ПОЛЬЗОВАТЕЛЬ**\n{analysis.user_visible}")
    lines.append(f"⚠️ **РИСК**\n{analysis.risk_label}")
    if analysis.dev_hypothesis:
        lines.append(f"💡 **ПРЕДПОЛОЖЕНИЕ**\n{analysis.dev_hypothesis}")
    if analysis.dev_questions:
        lines.append("❓ **ЧТО УТОЧНИТЬ У РАЗРАБОТЧИКА**")
        for q in analysis.dev_questions:
            lines.append(f"- {q}")
    lines.append(f"📋 **Название:** {analysis.tracker_title}")
    if analysis.glitchtip_url:
        lines.append(f"🔗 {analysis.glitchtip_url}")
    lines.append(format_history_span(analysis.history))
    return "\n\n".join(lines)


def format_analysis_plain(analysis: IssueAnalysisFull) -> str:
    lines = [f"🔍 ЧТО СЛУЧИЛОСЬ: {analysis.what_happened}"]
    if analysis.module:
        lines.append(f"📍 МОДУЛЬ: {analysis.module}")
    lines.append(f"💥 ЧТО ВИДИТ ПОЛЬЗОВАТЕЛЬ: {analysis.user_visible}")
    lines.append(f"⚠️ РИСК: {analysis.risk_label}")
    if analysis.dev_hypothesis:
        lines.append(f"💡 ПРЕДПОЛОЖЕНИЕ: {analysis.dev_hypothesis}")
    if analysis.dev_questions:
        lines.append("❓ УТОЧНИТЬ:")
        for q in analysis.dev_questions:
            lines.append(f"  • {q}")
    if analysis.glitchtip_url:
        lines.append(
            f'<a href="{analysis.glitchtip_url}" target="_blank" class="glitchtip-link">'
            "🔗 Открыть в Glitchtip</a>"
        )
    lines.append(format_history_span(analysis.history))
    return "<br/>".join(lines)


def _risk_label(title: str, issue: IssueRecord, severity: IssueSeverity) -> tuple[str, str]:
    if severity == IssueSeverity.BLOCKER and not is_stale(issue):
        if any(x in title for x in ("medicalcard", "integrity", "cannot assign null")):
            return "КРИТИЧНО", "risk-critical"
    if any(x in title for x in ("clickhouse", "file_put_contents", "rabbitmq")):
        return "НИЗКО", "risk-low"
    if severity in (IssueSeverity.BLOCKER, IssueSeverity.HIGH):
        return "СРЕДНЕ", "risk-medium"
    return "НИЗКО", "risk-low"


def _user_visible_one_of(title: str, issue: IssueRecord) -> str:
    if "clickhouse" in title or "file_put_contents" in title:
        return "Ошибка только в логах, пользователь ничего не замечает"
    if "rabbitmq" in title and issue.count < 50:
        return "Ошибка только в логах, пользователь ничего не замечает"
    if "sync" in title and ("calendar" in title or "admission" in title):
        return "Данные могут не отобразиться в календаре или основной системе"
    if issue.level == "fatal" or "cannot assign null" in title:
        return "Видит сообщение об ошибке, действие не выполняется"
    if "undefined array key" in title or "active record" in title:
        return "Данные не сохраняются без видимой причины"
    return "Видит сообщение об ошибке, действие не выполняется"
