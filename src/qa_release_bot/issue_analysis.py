from __future__ import annotations

from dataclasses import dataclass

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
    module_map: dict[str, str] | None = None,
) -> IssueAnalysisFull:
    reg = registry or IssueTitleRegistry()
    mapping = module_map or load_module_map()
    resolution = resolve_module(issue, mapping)
    title_lower = issue.title.lower()

    module_display = resolution.human_module
    what = _what_happened_plain(title_lower, issue)
    user_visible = _user_visible_one_of(title_lower, issue)
    risk_label, risk_css = _risk_label(title_lower, issue, severity)
    danger = risk_label
    questions = _dev_questions(title_lower, issue, module_display)
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
        tracker_title=tracker,
        history=history,
        is_stale=is_stale(issue),
        glitchtip_url=glitchtip_issue_url(glitchtip_base_url, issue.id),
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
    lines.append("❓ ЧТО УТОЧНИТЬ У РАЗРАБОТЧИКА:")
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


def _what_happened_plain(title: str, issue: IssueRecord) -> str:
    if "cannot assign null" in title:
        return (
            "При сохранении система получила пустое значение там, "
            "где ожидались обязательные данные — запись не завершается."
        )
    if "active record" in title and "новая" in title:
        return (
            "Система пытается изменить или удалить запись, которая ещё не была "
            "нормально сохранена в базе."
        )
    if "integrity constraint" in title or "1451" in title:
        return "Связанные записи в БД мешают удалить или изменить данные."
    if "hasattribute" in title and "null" in title:
        return "Получен пустой объект — форма могла отправиться до загрузки данных."
    if "undefined array key" in title:
        return "В запросе не хватает ожидаемого поля."
    if "rabbitmq" in title:
        return "Фоновые задачи не могут связаться с очередью сообщений."
    if "clickhouse" in title:
        return "Не удаётся записать аналитику в хранилище — на UI обычно не влияет."
    if "file_put_contents" in title:
        return "Сервер не может записать служебный файл (права или диск)."
    if issue.level == "fatal":
        return "Приложение аварийно прерывает обработку запроса."
    return "Ошибка не даёт завершить запрошенное действие."


def _user_visible_one_of(title: str, issue: IssueRecord) -> str:
    if "clickhouse" in title or "file_put_contents" in title:
        return "Ошибка только в логах, пользователь ничего не замечает"
    if "rabbitmq" in title and issue.count < 50:
        return "Ошибка только в логах, пользователь ничего не замечает"
    if issue.level == "fatal" or "cannot assign null" in title:
        return "Видит сообщение об ошибке, действие не выполняется"
    if "undefined array key" in title or "active record" in title:
        return "Данные не сохраняются без видимой причины"
    return "Видит сообщение об ошибке, действие не выполняется"


def _dev_questions(title: str, issue: IssueRecord, module: str | None) -> list[str]:
    mod = module or "этом модуле"
    qs = [
        f"В каком сценарии в {mod} вызывается эта ошибка?",
        "Какое действие пользователя в интерфейсе её запускает?",
    ]
    if "null" in title or "undefined" in title:
        qs.append("Какие поля формы должны быть заполнены?")
    else:
        qs.append("Есть ли тестовые данные на stage для воспроизведения?")
    return qs[:3]
