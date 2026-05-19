from datetime import datetime, timezone
from io import StringIO

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.markdown_report import AnalystReport, render_markdown
from qa_release_bot.release_decision import ReleaseDecision


def _issue(issue_id: str, title: str) -> IssueRecord:
    now = datetime.now(timezone.utc)
    return IssueRecord(
        id=issue_id,
        title=title,
        level="error",
        count=80,
        last_seen=now,
        first_seen=now,
        culprit="",
    )


def test_render_markdown_analyst_sections():
    report = AnalystReport(
        product_name="vetmanager-extjs",
        fetched_at=datetime.now(timezone.utc),
        decision=ReleaseDecision(
            verdict="risk",
            headline="⚠️ РЕЛИЗ С РИСКОМ",
            items=["[Медкарта] Тест"],
        ),
        blockers=[],
        highs=[
            _issue(
                "2",
                "TypeError: Cannot assign null to property Entity\\MedicalCard\\Diagnoses::$medicalCardId",
            )
        ],
        new_issues_stage=[],
        is_first_run=False,
    )
    text = render_markdown(report)
    assert "Появилось впервые" in text
    assert "Решение по релизу" in text
    assert "Блокеры" in text
    assert "медкарт" in text.lower() or "MedicalCard" in text
