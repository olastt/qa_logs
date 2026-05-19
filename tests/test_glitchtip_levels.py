from datetime import datetime, timezone

from qa_release_bot.glitchtip_levels import (
    level_display,
    split_by_glitchtip_level,
)
from qa_release_bot.issue_record import IssueRecord


def _issue(iid: str, level: str) -> IssueRecord:
    now = datetime.now(timezone.utc)
    return IssueRecord(
        id=iid,
        title=f"e{iid}",
        level=level,
        count=1,
        last_seen=now,
        first_seen=now,
        culprit="",
    )


def test_split_by_glitchtip_level_order():
    issues = [
        _issue("1", "info"),
        _issue("2", "fatal"),
        _issue("3", "error"),
        _issue("4", "critical"),
    ]
    sections = split_by_glitchtip_level(issues)
    assert [lvl for lvl, _ in sections] == ["fatal", "critical", "error", "info"]
    assert level_display("fatal") == "FATAL"
