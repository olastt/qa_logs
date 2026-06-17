from __future__ import annotations

from datetime import datetime, timezone

from qa_release_bot.config import Settings
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issue_watch import watch_new_issues


def _issue(issue_id: str, first_seen: datetime) -> IssueRecord:
    return IssueRecord(
        id=issue_id,
        title=f"Issue {issue_id}",
        level="error",
        count=1,
        last_seen=first_seen,
        first_seen=first_seen,
        culprit="",
        org_slug="vetmanager",
        project_slug="webappswidgets-test",
        project_id="42",
    )


def test_unseen_issue_is_alerted_only_when_first_seen_today(monkeypatch, tmp_path):
    old_issue = _issue("old", datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc))
    today_issue = _issue("today", datetime(2026, 6, 17, 12, 59, tzinfo=timezone.utc))
    issues_by_run = [
        [_issue("baseline", datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc))],
        [old_issue, today_issue],
        [old_issue, today_issue],
    ]

    monkeypatch.setattr(
        "qa_release_bot.new_issue_watch.build_summary_ref",
        lambda settings, cfg, name: {
            "name": name,
            "instance": "hetzner",
            "project": type(
                "Project",
                (),
                {"slug": "webappswidgets-test", "org_slug": "vetmanager"},
            )(),
        },
    )
    monkeypatch.setattr(
        "qa_release_bot.new_issue_watch.instance_credentials",
        lambda settings, instance: ("https://glitchtip.example", "token"),
    )
    monkeypatch.setattr(
        "qa_release_bot.new_issue_watch.report_fetch_options",
        lambda cfg: ("is:unresolved", "14d"),
    )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def fetch_issue_records(self, *args, **kwargs):
            return issues_by_run.pop(0)

    monkeypatch.setattr("qa_release_bot.new_issue_watch.GlitchtipClient", FakeClient)

    state = tmp_path / "watch.db"
    reference_at = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
    watch_new_issues(
        Settings(),
        ["hetzner-webappswidgets-test"],
        state_db_path=state,
        reference_at=reference_at,
    )
    result = watch_new_issues(
        Settings(),
        ["hetzner-webappswidgets-test"],
        state_db_path=state,
        reference_at=reference_at,
    )
    repeated = watch_new_issues(
        Settings(),
        ["hetzner-webappswidgets-test"],
        state_db_path=state,
        reference_at=reference_at,
    )

    assert [alert.issue.id for alert in result.alerts] == ["today"]
    assert repeated.alerts == []
