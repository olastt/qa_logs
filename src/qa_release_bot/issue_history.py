from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.tuesday_diff import is_stale


@dataclass(slots=True)
class IssueHistory:
    exists_days: int
    first_seen_label: str
    count: int
    avg_per_day: float
    last_seen_label: str
    dynamics: str


def build_issue_history(issue: IssueRecord) -> IssueHistory:
    now = datetime.now(timezone.utc)
    first = _aware(issue.first_seen)
    last = _aware(issue.last_seen)
    exists_days = max(1, (now - first).days)
    avg = issue.count / exists_days

    dynamics = _dynamics(issue, exists_days, avg)

    return IssueHistory(
        exists_days=exists_days,
        first_seen_label=_fmt_ru(first),
        count=issue.count,
        avg_per_day=round(avg, 1),
        last_seen_label=_fmt_ru(last),
        dynamics=dynamics,
    )


def format_history(h: IssueHistory) -> str:
    return (
        f"📅 Существует: {h.exists_days} дн. (с {h.first_seen_label})\n"
        f"🔁 Повторений: {h.count} (в среднем ~{h.avg_per_day} в день)\n"
        f"👁 Последний раз: {h.last_seen_label}\n"
        f"📈 Динамика: {h.dynamics}"
    )


def format_history_span(h: IssueHistory) -> str:
    """Краткая история с диапазоном дат: с 10 апреля → 19 мая."""
    return (
        f"📅 Существует: {h.exists_days} дн. (с {h.first_seen_label} → {h.last_seen_label})\n"
        f"🔁 Повторений: {h.count} (в среднем ~{h.avg_per_day} в день)\n"
        f"📈 Динамика: {h.dynamics}"
    )


def _dynamics(issue: IssueRecord, exists_days: int, avg_per_day: float) -> str:
    if is_stale(issue):
        return "⚪ STALE — вероятно уже исправлено"
    if exists_days >= 14 and avg_per_day < 2 and issue.count > 20:
        return "🟡 Хроническая проблема"
    if issue.count > exists_days * 3 and not is_stale(issue, days=7):
        return "🔴 Активно растёт — срочно"
    if avg_per_day < 1 and exists_days > 7:
        return "🟢 Затухает — вероятно фиксят"
    if not is_stale(issue, days=7):
        return "🔴 Активно растёт — срочно"
    return "🟡 Хроническая проблема"


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_ru(dt: datetime) -> str:
    from qa_release_bot.html_dates import fmt_datetime_ru

    d = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return fmt_datetime_ru(d)
