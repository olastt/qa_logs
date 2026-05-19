from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issues import find_new_issues_first_seen_today

MSK = ZoneInfo("Europe/Moscow")


def _issue(iid: str, first: datetime) -> IssueRecord:
    return IssueRecord(
        id=iid,
        title=f"Error {iid}",
        level="error",
        count=1,
        last_seen=first,
        first_seen=first,
        culprit="App\\Foo::bar",
        org_slug="vetmanager",
        project_id="14",
    )


def test_first_seen_today_msk():
    ref = datetime(2026, 5, 19, 20, 0, tzinfo=timezone.utc)
    today_msk = datetime(2026, 5, 19, 10, 0, tzinfo=MSK).astimezone(timezone.utc)
    yesterday_msk = datetime(2026, 5, 18, 23, 0, tzinfo=MSK).astimezone(timezone.utc)
    issues = [_issue("1", today_msk), _issue("2", yesterday_msk)]
    new = find_new_issues_first_seen_today(
        issues, reference_at=ref, environment="test"
    )
    assert len(new) == 1
    assert new[0].issue.id == "1"
    assert "сегодня" in new[0].deploy_hint
