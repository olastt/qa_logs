from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.noise_groups import _normalize_title


@dataclass(slots=True)
class DiffRow:
    title: str
    prev_count: int | None
    curr_count: int | None
    delta_pct: str
    status: str


def build_stage_diff(
    current: list[IssueRecord],
    previous: list[IssueRecord] | None,
) -> list[DiffRow]:
    if not previous:
        return []

    prev_map = {_normalize_title(i.title): i for i in previous}
    curr_map = {_normalize_title(i.title): i for i in current}
    all_keys = sorted(set(prev_map) | set(curr_map))

    rows: list[DiffRow] = []
    for key in all_keys:
        prev = prev_map.get(key)
        curr = curr_map.get(key)
        title = (curr or prev).title if (curr or prev) else key
        p_count = prev.count if prev else None
        c_count = curr.count if curr else None
        status = _diff_status(prev, curr)
        delta = _delta_pct(p_count, c_count)
        rows.append(
            DiffRow(
                title=title[:80],
                prev_count=p_count,
                curr_count=c_count,
                delta_pct=delta,
                status=status,
            )
        )
    return sorted(rows, key=lambda r: r.status)


def _delta_pct(prev: int | None, curr: int | None) -> str:
    if prev is None and curr is not None:
        return "новый"
    if prev is not None and curr is None:
        return "-100%"
    if prev is None or curr is None or prev == 0:
        return "—"
    change = ((curr - prev) / prev) * 100
    if change > 0:
        return f"+{change:.0f}%"
    return f"{change:.0f}%"


def _diff_status(prev: IssueRecord | None, curr: IssueRecord | None) -> str:
    if prev is None and curr is not None:
        if is_stale(curr):
            return "🕰️ stale"
        return "🆕 новый"
    if prev is not None and curr is None:
        return "✅ исправлен"
    if prev and curr:
        if is_stale(curr):
            return "🕰️ stale"
        if prev.count > 0 and curr.count > prev.count * 1.5:
            return "📈 растёт"
        if prev.count > 0 and curr.count < prev.count * 0.5:
            return "📉 падает"
        if curr.count > prev.count * 2:
            return "⚠️ регрессия"
    return "➖ без изменений"


def is_stale(issue: IssueRecord, *, days: int = 30) -> bool:
    now = datetime.now(timezone.utc)
    seen = issue.last_seen
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (now - seen) > timedelta(days=days)


def is_recent(issue: IssueRecord, *, days: int = 7) -> bool:
    now = datetime.now(timezone.utc)
    seen = issue.last_seen
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (now - seen) <= timedelta(days=days)
