from datetime import datetime, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issues import find_new_issues_by_id


def _issue(iid: str) -> IssueRecord:
    now = datetime.now(timezone.utc)
    return IssueRecord(
        id=iid,
        title=f"Error {iid}",
        level="error",
        count=1,
        last_seen=now,
        first_seen=now,
        culprit="",
    )


def test_new_by_id():
    prev = [_issue("1"), _issue("2")]
    curr = [_issue("1"), _issue("3")]
    new = find_new_issues_by_id(curr, prev, environment="stage")
    assert len(new) == 1
    assert new[0].issue.id == "3"
