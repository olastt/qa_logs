from datetime import datetime, timezone
from pathlib import Path

from qa_release_bot.html_report import (
    HtmlPageContext,
    build_analyst_html_context,
    render_html,
    write_analyst_html,
)
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.markdown_report import AnalystReport
from qa_release_bot.release_decision import ReleaseDecision


def test_render_html_contains_design_elements():
    now = datetime.now(timezone.utc)
    report = AnalystReport(
        product_name="vetmanager-extjs",
        fetched_at=now,
        decision=ReleaseDecision(verdict="ok", headline="✅ РЕЛИЗ ОК", items=[]),
        blockers=[],
        highs=[
            IssueRecord(
                id="1",
                title="TypeError test",
                level="error",
                count=10,
                last_seen=now,
                first_seen=now,
                culprit="",
                org_slug="vetmanager",
                project_slug="vetmanager-extjs-test",
                project_id="14",
            )
        ],
        mediums=[
            IssueRecord(
                id="2",
                title="Undefined array key foo",
                level="warning",
                count=3,
                last_seen=now,
                first_seen=now,
                culprit="",
            )
        ],
    )
    ctx = build_analyst_html_context(
        report, glitchtip_base_url="https://glitchtip.example"
    )
    html = render_html(ctx)
    assert "Unbounded" in html
    assert "Chart.js" in html
    assert "chartSeverity" in html
    assert "bar-track" in html
    assert "QA Release Report" in html
    assert "■■" not in html
    assert "glitchtip-link" in html
    assert "https://glitchtip.example/vetmanager/issues/1?project=14" in html
    assert "Впервые" in html
    assert "добавить в карту модулей" not in html


def test_write_analyst_html_file(tmp_path: Path):
    now = datetime.now(timezone.utc)
    report = AnalystReport(
        product_name="vetmanager-extjs",
        fetched_at=now,
        decision=ReleaseDecision(verdict="ok", headline="✅", items=[]),
    )
    path = tmp_path / "qa_report_2026-05-19.html"
    write_analyst_html(report, path)
    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
