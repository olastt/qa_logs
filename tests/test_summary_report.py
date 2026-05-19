from datetime import datetime, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.release_decision import ReleaseDecision
from qa_release_bot.summary_report import SummaryReport, render_summary_markdown
from qa_release_bot.summary_pdf import default_summary_pdf_path, write_summary_pdf
from qa_release_bot.pdf_fonts import find_font_path


def test_render_summary_markdown_no_diff_sections():
    now = datetime.now(timezone.utc)
    issue = IssueRecord(
        id="1",
        title="TypeError in widget",
        level="error",
        count=10,
        last_seen=now,
        first_seen=now,
        culprit="",
    )
    report = SummaryReport(
        product_name="webapps-widgets-test",
        instance="selectel",
        project_slug="webappswidgets-test",
        fetched_at=now,
        decision=ReleaseDecision(verdict="ok", headline="✅ Критичных нет", items=[]),
        total_unresolved=1,
        highs=[issue],
        is_first_run=True,
    )
    md = render_summary_markdown(report)
    assert "Сводка логов" in md
    assert "webappswidgets-test" in md
    assert "Дифф" not in md
    assert "STAGE" not in md
    assert "Первый запуск" in md
    assert "TypeError" in md or "widget" in md


def test_write_summary_pdf(tmp_path):
    if find_font_path() is None:
        import pytest

        pytest.skip("TTF font not available")
    now = datetime.now(timezone.utc)
    report = SummaryReport(
        product_name="webapps-widgets-test",
        instance="selectel",
        project_slug="webappswidgets-test",
        fetched_at=now,
        decision=ReleaseDecision(verdict="ok", headline="✅ Критичных нет", items=[]),
        total_unresolved=5,
        mediums=[
            IssueRecord(
                id="2",
                title="Warning in widget",
                level="warning",
                count=3,
                last_seen=now,
                first_seen=now,
                culprit="",
            )
        ],
    )
    path = default_summary_pdf_path(tmp_path, report)
    result = write_summary_pdf(report, path)
    assert path.is_file()
    assert result.page_count >= 1
    assert result.mediums == 1
