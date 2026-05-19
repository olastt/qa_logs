from datetime import datetime, timezone

from qa_release_bot.grouper import group_issues
from qa_release_bot.models import GlitchtipIssue, GlitchtipProjectRef


def _issue(issue_id: str, exc_type: str = "Error") -> GlitchtipIssue:
    project = GlitchtipProjectRef(instance="hetzner", org_slug="vetmanager", slug="app")
    now = datetime.now(timezone.utc)
    return GlitchtipIssue(
        id=issue_id,
        short_id=issue_id,
        project=project,
        title="boom",
        culprit="",
        level="error",
        status="unresolved",
        count=1,
        user_count=0,
        first_seen=now,
        last_seen=now,
        metadata={"type": exc_type, "value": "same", "filename": "a.dart", "function": "f"},
    )


def test_group_issues_same_fingerprint():
    groups = group_issues([_issue("1"), _issue("2")])
    assert len(groups) == 1
    assert len(groups[0].issues) == 2


def test_group_issues_different_fingerprint():
    groups = group_issues([_issue("1", "A"), _issue("2", "B")])
    assert len(groups) == 2
