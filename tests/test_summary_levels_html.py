from datetime import datetime, timezone

from qa_release_bot.html_report import build_summary_html_context, render_html
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.release_decision import decide_summary_by_level
from qa_release_bot.summary_report import SummaryReport


def test_summary_html_sections_by_glitchtip_level():
    now = datetime.now(timezone.utc)
    fatal = IssueRecord(
        id="1",
        title="Fatal crash",
        level="fatal",
        count=5,
        last_seen=now,
        first_seen=now,
        culprit="",
        org_slug="vetmanager",
        project_id="15",
    )
    error = IssueRecord(
        id="2",
        title="Error in API",
        level="error",
        count=2,
        last_seen=now,
        first_seen=now,
        culprit="",
        org_slug="vetmanager",
        project_id="15",
    )
    sections = [("fatal", [fatal]), ("error", [error])]
    report = SummaryReport(
        product_name="app-test",
        instance="hetzner",
        project_slug="app-test",
        fetched_at=now,
        decision=decide_summary_by_level(sections),
        total_unresolved=2,
        level_sections=sections,
    )
    html = render_html(
        build_summary_html_context(report, glitchtip_base_url="https://glitchtip.example")
    )
    assert "FATAL (1)" in html
    assert "ERROR (1)" in html
    assert "sev-badge" in html
    assert "BLOCKER" not in html or "🔴 Блокеры" not in html
