from datetime import datetime, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.issue_titles import IssueTitleRegistry, generate_tracker_title
from qa_release_bot.module_map import resolve_module


def test_registry_makes_duplicate_titles_unique():
    reg = IssueTitleRegistry()
    resolution = resolve_module(
        IssueRecord(
            id="1",
            title="Generic error",
            level="error",
            count=1,
            last_seen=datetime.now(timezone.utc),
            first_seen=datetime.now(timezone.utc),
            culprit="",
        )
    )
    issue_a = IssueRecord(
        id="1",
        title="Generic error",
        level="error",
        count=1,
        last_seen=datetime.now(timezone.utc),
        first_seen=datetime.now(timezone.utc),
        culprit="FooController::index",
    )
    issue_b = IssueRecord(
        id="2",
        title="Generic error",
        level="error",
        count=2,
        last_seen=datetime.now(timezone.utc),
        first_seen=datetime.now(timezone.utc),
        culprit="BarController::index",
    )
    t1 = generate_tracker_title(issue_a, resolution, reg)
    t2 = generate_tracker_title(issue_b, resolution, reg)
    assert t1 != t2


def test_glitchtip_url_format():
    from qa_release_bot.issue_titles import glitchtip_issue_url

    assert glitchtip_issue_url("https://glitchtip.example/", "42") == (
        "https://glitchtip.example/issues/42/"
    )
