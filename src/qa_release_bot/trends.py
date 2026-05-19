from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.noise_groups import _normalize_title
from qa_release_bot.snapshot_store import SnapshotStore


@dataclass(slots=True)
class TrendItem:
    title: str
    total_count: int
    weekly_counts: list[int]
    growing: bool


def build_trends(store: SnapshotStore, env: str = "stage", weeks: int = 4) -> list[TrendItem]:
    dates = sorted(store.list_dates(env, limit=weeks))[-weeks:]
    if len(dates) < 2:
        return []

    by_title: dict[str, list[int]] = defaultdict(list)
    titles: dict[str, str] = {}

    for d in dates:
        snap = store.load(env, d) or []
        week_counts: dict[str, int] = defaultdict(int)
        for issue in snap:
            key = _normalize_title(issue.title)
            week_counts[key] += issue.count
            titles[key] = issue.title
        for key in week_counts:
            by_title[key].append(week_counts[key])

    items: list[TrendItem] = []
    for key, counts in by_title.items():
        if len(counts) < 2:
            continue
        total = sum(counts)
        growing = all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1)) and counts[-1] > counts[0]
        items.append(
            TrendItem(
                title=titles[key][:80],
                total_count=total,
                weekly_counts=counts,
                growing=growing,
            )
        )

    return sorted(items, key=lambda x: -x.total_count)[:5]
