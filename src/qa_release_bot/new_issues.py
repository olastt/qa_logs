from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from qa_release_bot.issue_analysis import analyze_issue_full
from qa_release_bot.issue_titles import IssueTitleRegistry
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.severity_rules import IssueSeverity, classify_severity


@dataclass(slots=True)
class NewIssueItem:
    issue: IssueRecord
    environment: str
    severity: IssueSeverity
    tracker_title: str
    deploy_hint: str


def find_new_issues_by_id(
    current: list[IssueRecord],
    previous: list[IssueRecord] | None,
    *,
    environment: str,
    last_deploy: date | None = None,
    registry: IssueTitleRegistry | None = None,
    glitchtip_base_url: str = "",
) -> list[NewIssueItem]:
    if previous is None:
        return []

    prev_ids = {str(i.id) for i in previous}
    items: list[NewIssueItem] = []

    for issue in current:
        if str(issue.id) in prev_ids:
            continue
        sev = classify_severity(issue)
        analysis = analyze_issue_full(
            issue, sev, registry=registry, glitchtip_base_url=glitchtip_base_url
        )
        items.append(
            NewIssueItem(
                issue=issue,
                environment=environment,
                severity=sev,
                tracker_title=analysis.tracker_title,
                deploy_hint=_deploy_hint(issue, last_deploy),
            )
        )

    order = {
        IssueSeverity.BLOCKER: 0,
        IssueSeverity.HIGH: 1,
        IssueSeverity.MEDIUM: 2,
        IssueSeverity.LOW: 3,
    }
    return sorted(items, key=lambda x: (order[x.severity], -x.issue.count))


def _deploy_hint(issue: IssueRecord, last_deploy: date | None) -> str:
    if not last_deploy:
        return "сравните first_seen с датой последнего деплоя вручную"
    first = issue.first_seen
    if first.tzinfo:
        first_d = first.astimezone(timezone.utc).date()
    else:
        first_d = first.date()
    if first_d >= last_deploy:
        return f"first_seen ({first_d}) после деплоя ({last_deploy}) — возможна связь с выкатом"
    return f"first_seen ({first_d}) до деплоя ({last_deploy}) — скорее старый, но новый в снапшоте"
