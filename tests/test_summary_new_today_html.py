from datetime import datetime, timezone

from qa_release_bot.html_report import build_summary_html_context, render_html
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.new_issues import NewIssueItem
from qa_release_bot.release_decision import decide_summary
from qa_release_bot.severity_rules import IssueSeverity
from qa_release_bot.summary_report import SummaryReport


def test_summary_first_run_still_shows_today_issues():
    now = datetime.now(timezone.utc)
    issue = IssueRecord(
        id="5536",
        title="Fresh error today",
        level="error",
        count=1,
        last_seen=now,
        first_seen=now,
        culprit="",
        org_slug="vetmanager",
        project_id="15",
    )
    report = SummaryReport(
        product_name="test",
        instance="hetzner",
        project_slug="app-test",
        fetched_at=now,
        decision=decide_summary([], []),
        total_unresolved=1,
        is_first_run=True,
        new_issues=[
            NewIssueItem(
                issue=issue,
                environment="test",
                severity=IssueSeverity.HIGH,
                tracker_title="[ExtJS] Fresh error",
                deploy_hint="впервые зафиксирован сегодня",
            )
        ],
    )
    ctx = build_summary_html_context(
        report, glitchtip_base_url="https://glitchtip.example"
    )
    html = render_html(ctx)
    assert "Первый запуск" not in html or "Новые логи появятся" not in html
    assert "Новые логи за сегодня" in html
    assert "issue-card" in html
    assert "Fresh error" in html or "5536" in html
