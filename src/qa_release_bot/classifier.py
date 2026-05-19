from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_release_bot.models import GlitchtipIssue, IssueGroup, ReleaseVerdict
from qa_release_bot.storage import IssueStateStore


# Пороги — заглушки; вынесем в config/rules.yaml
_BLOCKER_LEVELS = frozenset({"fatal", "error"})
_HIGH_VOLUME_COUNT = 100
_REGRESSION_WINDOW = timedelta(days=7)


def classify_issue(issue: GlitchtipIssue, store: IssueStateStore) -> tuple[ReleaseVerdict, str]:
    """
    Эвристики v0 для вердикта по одному issue.

    - fatal / много событий → blocker
    - issue был известен, снова активен недавно → regression
    - иначе → defer
    """
    if issue.level in _BLOCKER_LEVELS and issue.count >= _HIGH_VOLUME_COUNT:
        return ReleaseVerdict.BLOCKER, f"level={issue.level}, events={issue.count}"

    if issue.level == "fatal":
        return ReleaseVerdict.BLOCKER, f"fatal: {issue.title[:80]}"

    was_known = store.is_known(issue.project.instance, issue.project.slug, issue.id)
    if was_known and _is_recent(issue.last_seen, _REGRESSION_WINDOW):
        return ReleaseVerdict.REGRESSION, "issue снова активен после паузы"

    return ReleaseVerdict.DEFER, "низкий приоритет по эвристикам v0"


def classify_group(group: IssueGroup, store: IssueStateStore) -> IssueGroup:
    """Вердикт группы = самый строгий среди issues."""
    priority = {
        ReleaseVerdict.BLOCKER: 0,
        ReleaseVerdict.REGRESSION: 1,
        ReleaseVerdict.DEFER: 2,
    }
    best_verdict = ReleaseVerdict.DEFER
    best_reason = ""
    for issue in group.issues:
        verdict, reason = classify_issue(issue, store)
        if priority[verdict] < priority[best_verdict]:
            best_verdict = verdict
            best_reason = reason
    group.verdict = best_verdict
    group.verdict_reason = best_reason
    return group


def _is_recent(dt: datetime, window: timedelta) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt <= window
