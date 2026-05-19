from datetime import datetime, timezone

from qa_release_bot.grouper import dedupe_by_title, group_by_title
from qa_release_bot.models import NormalizedIssue


def _norm(issue_id: str, title: str) -> NormalizedIssue:
    now = datetime.now(timezone.utc)
    return NormalizedIssue(
        id=issue_id,
        short_id=issue_id,
        title=title,
        level="error",
        count=1,
        last_seen=now,
        stack_trace=None,
        environment="test",
        project_slug="p",
        instance="hetzner",
    )


def test_group_by_title_merges_duplicates():
    issues = [_norm("1", "Same"), _norm("2", "Same"), _norm("3", "Other")]
    groups = group_by_title(issues)
    assert len(groups) == 2
    same = next(g for g in groups if g.title == "Same")
    assert len(same.issues) == 2
    assert same.duplicate_ids == 1


def test_dedupe_by_title():
    issues = [_norm("1", "A"), _norm("2", "A")]
    deduped = dedupe_by_title(issues)
    assert len(deduped) == 1
