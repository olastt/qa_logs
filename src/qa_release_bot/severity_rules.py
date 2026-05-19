from __future__ import annotations

from enum import StrEnum

from qa_release_bot.issue_record import IssueRecord


class IssueSeverity(StrEnum):
    BLOCKER = "blocker"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def classify_severity(issue: IssueRecord) -> IssueSeverity:
    level = issue.level.lower()
    count = issue.count
    if level == "fatal" or (level == "error" and count > 200):
        return IssueSeverity.BLOCKER
    if level == "error" and 50 <= count <= 199:
        return IssueSeverity.HIGH
    if (level == "error" and 10 <= count <= 49) or (level == "warning" and count > 20):
        return IssueSeverity.MEDIUM
    return IssueSeverity.LOW
