from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from qa_release_bot.issue_record import IssueRecord


@dataclass(slots=True)
class GroupedNoise:
    label: str
    total_count: int
    issue_count: int


def is_file_put_contents(title: str) -> bool:
    return "file_put_contents" in title.lower()


def is_clickhouse(title: str) -> bool:
    t = title.lower()
    return "clickhouse" in t


def group_noise_issues(issues: list[IssueRecord]) -> tuple[list[IssueRecord], list[GroupedNoise]]:
    file_puts: list[IssueRecord] = []
    clickhouse: list[IssueRecord] = []
    rest: list[IssueRecord] = []

    for issue in issues:
        if is_file_put_contents(issue.title):
            file_puts.append(issue)
        elif is_clickhouse(issue.title):
            clickhouse.append(issue)
        else:
            rest.append(issue)

    grouped: list[GroupedNoise] = []
    if file_puts:
        n = len(file_puts)
        grouped.append(
            GroupedNoise(
                label=f"⚠️ file_put_contents: {n} вхождений — вероятно проблема с очисткой tmp-файлов",
                total_count=sum(i.count for i in file_puts),
                issue_count=n,
            )
        )
    if clickhouse:
        n = len(clickhouse)
        grouped.append(
            GroupedNoise(
                label=f"⚠️ ClickHouse: {n} вхождений — логи/аналитика недоступны",
                total_count=sum(i.count for i in clickhouse),
                issue_count=n,
            )
        )

    return dedupe_by_title(rest), grouped


def dedupe_by_title(issues: list[IssueRecord]) -> list[IssueRecord]:
    buckets: dict[str, IssueRecord] = {}
    for issue in issues:
        key = _normalize_title(issue.title)
        if key not in buckets:
            buckets[key] = issue
            continue
        prev = buckets[key]
        buckets[key] = IssueRecord(
            id=prev.id,
            title=prev.title,
            level=_max_level(prev.level, issue.level),
            count=prev.count + issue.count,
            last_seen=max(prev.last_seen, issue.last_seen),
            first_seen=_earlier(prev.first_seen, issue.first_seen),
            culprit=issue.culprit or prev.culprit,
            stack_frames=issue.stack_frames or prev.stack_frames,
            metadata=issue.metadata or prev.metadata,
        )
    return list(buckets.values())


def _normalize_title(title: str) -> str:
    t = re.sub(r"/var/www/vetmanager/build/tasks/\d+", "/.../tasks/*", title)
    return re.sub(r"\s+", " ", t).strip().lower()


def _max_level(a: str, b: str) -> str:
    order = {"fatal": 4, "error": 3, "warning": 2, "info": 1}
    return a if order.get(a.lower(), 0) >= order.get(b.lower(), 0) else b


def _earlier(a: datetime, b: datetime) -> datetime:
    return a if a <= b else b
