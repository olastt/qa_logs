from datetime import datetime, timezone

from qa_release_bot.issue_plain_explain import explain_for_tester
from qa_release_bot.issue_record import IssueRecord


def _issue(*, title: str = "Error", count: int = 3, metadata: dict | None = None) -> IssueRecord:
    now = datetime.now(timezone.utc)
    return IssueRecord(
        id="1",
        title=title,
        level="error",
        count=count,
        last_seen=now,
        first_seen=now,
        culprit="",
        metadata=metadata or {},
    )


def test_max_execution_time_with_cache_lock():
    issue = _issue(
        title="FatalError",
        metadata={
            "value": "Maximum execution time of 30 seconds exceeded",
            "log_messages": [
                "Waiting for cache lock on key vetmanager_cache_config",
            ],
        },
    )
    exp = explain_for_tester(issue)
    assert "30" in exp.one_liner
    assert "блокировк" in exp.one_liner.lower() or "lock" in exp.one_liner.lower()
    assert "кеш" in exp.one_liner.lower() or "cache" in exp.one_liner.lower()
    assert exp.why


def test_undefined_array_key():
    issue = _issue(
        title="ErrorException",
        metadata={
            "value": 'Undefined array key "clinicId"',
        },
    )
    exp = explain_for_tester(issue)
    assert "clinicId" in exp.one_liner or "поля" in exp.one_liner.lower()
    assert "не хватает" in exp.one_liner.lower() or "неполн" in exp.why.lower()


def test_summary_html_shows_plain_explain():
    from qa_release_bot.html_report import build_summary_html_context, render_html
    from qa_release_bot.new_issues import NewIssueItem
    from qa_release_bot.release_decision import decide_summary
    from qa_release_bot.severity_rules import IssueSeverity
    from qa_release_bot.summary_report import SummaryReport

    now = datetime.now(timezone.utc)
    issue = IssueRecord(
        id="5536",
        title="FatalError",
        level="error",
        count=2,
        last_seen=now,
        first_seen=now,
        culprit="/var/www/app/cache.php",
        org_slug="vetmanager",
        project_id="15",
        metadata={
            "value": "Maximum execution time of 30 seconds exceeded",
            "log_messages": ["Waiting for flock on cache lock"],
        },
    )
    report = SummaryReport(
        product_name="vetmanager",
        instance="hetzner",
        project_slug="app-test",
        fetched_at=now,
        decision=decide_summary([], []),
        total_unresolved=1,
        new_issues=[
            NewIssueItem(
                issue=issue,
                environment="test",
                severity=IssueSeverity.HIGH,
                tracker_title="[Cache] lock timeout",
                deploy_hint="впервые зафиксирован сегодня",
            )
        ],
    )
    ctx = build_summary_html_context(report, glitchtip_base_url="https://glitchtip.example")
    html = render_html(ctx)
    assert "Если упростить" in html
    assert "Почему появилась" in html
    assert "30" in html
