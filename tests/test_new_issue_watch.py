from __future__ import annotations

from datetime import datetime, timezone

from qa_release_bot.config import Settings
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issue_watch import format_new_issue_watch_notify, watch_new_issues


def _issue(
    issue_id: str,
    title: str = "Server Error",
    *,
    first_seen: datetime | None = None,
) -> IssueRecord:
    seen = first_seen or datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc)
    return IssueRecord(
        id=issue_id,
        title=title,
        level="error",
        count=1,
        last_seen=seen,
        first_seen=seen,
        culprit="",
        org_slug="vetmanager",
        project_slug="webappswidgets-test",
        project_id="42",
    )


def test_new_issue_watch_baselines_first_run(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "qa_release_bot.new_issue_watch.build_summary_ref",
        lambda settings, cfg, name: {
            "name": name,
            "instance": "hetzner",
            "project": type(
                "Project",
                (),
                {
                    "slug": "webappswidgets-test",
                    "org_slug": "vetmanager",
                    "label": None,
                },
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
            return [_issue("1")]

    monkeypatch.setattr("qa_release_bot.new_issue_watch.GlitchtipClient", FakeClient)

    state = tmp_path / "watch.db"
    first = watch_new_issues(Settings(), ["hetzner-webappswidgets-test"], state_db_path=state)
    second = watch_new_issues(Settings(), ["hetzner-webappswidgets-test"], state_db_path=state)

    assert first.baseline_created is True
    assert first.alerts == []
    assert second.baseline_created is False
    assert second.alerts == []


def test_new_issue_watch_reports_only_after_baseline(monkeypatch, tmp_path):
    issues_by_run = [[_issue("1")], [_issue("1"), _issue("2", "Brand new")]]

    monkeypatch.setattr(
        "qa_release_bot.new_issue_watch.build_summary_ref",
        lambda settings, cfg, name: {
            "name": name,
            "instance": "hetzner",
            "project": type(
                "Project",
                (),
                {
                    "slug": "webappswidgets-test",
                    "org_slug": "vetmanager",
                    "label": "webapps(widgets)-review-feature-test",
                },
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
    reference_at = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
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
    text = format_new_issue_watch_notify(result)

    assert [alert.issue.id for alert in result.alerts] == ["2"]
    assert "Brand new" in text
    assert "🆕 QA Bot: новые ошибки в Glitchtip — 1" in text
    assert "Проверено проектов: 1" in text
    assert "Проект: [hetzner] webapps(widgets)-review-feature-test" in text
    assert "Первое появление в Glitchtip: 2026-06-14 13:00 МСК" in text
    assert "Обнаружено ботом:" in text
