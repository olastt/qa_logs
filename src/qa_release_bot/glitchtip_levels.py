"""Группировка issue по полю Level из Glitchtip."""

from __future__ import annotations

from qa_release_bot.issue_record import IssueRecord

# Порядок секций в сводке (сверху вниз).
LEVEL_ORDER: tuple[str, ...] = (
    "fatal",
    "critical",
    "error",
    "warning",
    "info",
    "debug",
    "sample",
)

_LEVEL_BADGE: dict[str, tuple[str, str, str]] = {
    "fatal": ("FATAL", "red", "#f96b6b"),
    "critical": ("CRITICAL", "red", "#e11d48"),
    "error": ("ERROR", "amber", "#f5a623"),
    "warning": ("WARNING", "purple", "#a78bfa"),
    "info": ("INFO", "green", "#3ecf8e"),
    "debug": ("DEBUG", "muted", "#7b7f91"),
    "sample": ("SAMPLE", "muted", "#818cf8"),
}


def normalize_level(level: str) -> str:
    return (level or "unknown").strip().lower() or "unknown"


def level_sort_index(level: str) -> int:
    key = normalize_level(level)
    if key in LEVEL_ORDER:
        return LEVEL_ORDER.index(key)
    return len(LEVEL_ORDER) + 1


def level_display(level: str) -> str:
    return normalize_level(level).upper()


def level_badge(level: str) -> tuple[str, str, str]:
    key = normalize_level(level)
    return _LEVEL_BADGE.get(key, (level_display(level), "muted", "#818cf8"))


def split_by_glitchtip_level(
    issues: list[IssueRecord],
) -> list[tuple[str, list[IssueRecord]]]:
    """Секции по Level из лога, внутри секции — по убыванию count."""
    buckets: dict[str, list[IssueRecord]] = {}
    for issue in issues:
        key = normalize_level(issue.level)
        buckets.setdefault(key, []).append(issue)

    known = [lvl for lvl in LEVEL_ORDER if buckets.get(lvl)]
    extra = sorted(
        (lvl for lvl in buckets if lvl not in LEVEL_ORDER),
        key=level_sort_index,
    )
    order = known + extra
    return [
        (lvl, sorted(buckets[lvl], key=lambda i: -i.count))
        for lvl in order
        if buckets.get(lvl)
    ]


def total_in_sections(sections: list[tuple[str, list[IssueRecord]]]) -> int:
    return sum(len(issues) for _, issues in sections)
