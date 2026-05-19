from __future__ import annotations

from dataclasses import dataclass

from qa_release_bot.issue_analysis import analyze_issue_full
from qa_release_bot.issue_titles import IssueTitleRegistry
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.severity_rules import IssueSeverity, classify_severity
from qa_release_bot.tuesday_diff import is_stale


@dataclass(slots=True)
class ReleaseDecision:
    verdict: str  # forbidden | risk | ok
    headline: str
    items: list[str]


def decide_release(
    blockers: list[IssueRecord],
    highs: list[IssueRecord],
    *,
    registry: IssueTitleRegistry | None = None,
) -> ReleaseDecision:
    active_blockers = [i for i in blockers if not is_stale(i)]
    active_highs = [i for i in highs if not is_stale(i)]

    if active_blockers:
        names = [_tracker_title(i, registry) for i in active_blockers[:12]]
        return ReleaseDecision(
            verdict="forbidden",
            headline="🚫 **РЕЛИЗ ЗАПРЕЩЁН**",
            items=names,
        )
    if active_highs:
        names = [_tracker_title(i, registry) for i in active_highs[:12]]
        return ReleaseDecision(
            verdict="risk",
            headline="⚠️ **РЕЛИЗ С РИСКОМ** — команда должна принять риск:",
            items=names,
        )
    known = [_tracker_title(i, registry) for i in (blockers + highs)[:8] if is_stale(i)]
    return ReleaseDecision(
        verdict="ok",
        headline="✅ **РЕЛИЗ ОК**",
        items=known if known else ["Критичных активных blocker/high нет (STALE не учитывались)."],
    )


def _tracker_title(issue: IssueRecord, registry: IssueTitleRegistry | None) -> str:
    return analyze_issue_full(
        issue, classify_severity(issue), registry=registry
    ).tracker_title


def split_by_severity(issues: list[IssueRecord]) -> dict[IssueSeverity, list[IssueRecord]]:
    buckets: dict[IssueSeverity, list[IssueRecord]] = {
        IssueSeverity.BLOCKER: [],
        IssueSeverity.HIGH: [],
        IssueSeverity.MEDIUM: [],
        IssueSeverity.LOW: [],
    }
    for issue in issues:
        buckets[classify_severity(issue)].append(issue)
    for sev in buckets:
        buckets[sev].sort(key=lambda i: -i.count)
    return buckets
