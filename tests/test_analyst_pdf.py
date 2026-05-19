from datetime import datetime, timezone
from pathlib import Path

import pytest

from qa_release_bot.analyst_pdf import write_analyst_pdf
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.markdown_report import AnalystReport
from qa_release_bot.pdf_fonts import find_font_path
from qa_release_bot.release_decision import ReleaseDecision


def _minimal_report() -> AnalystReport:
    now = datetime.now(timezone.utc)
    issue = IssueRecord(
        id="1",
        title="TypeError: Cannot assign null to property Entity\\MedicalCard",
        level="error",
        count=80,
        last_seen=now,
        first_seen=now,
        culprit="",
    )
    return AnalystReport(
        product_name="vetmanager-extjs",
        fetched_at=now,
        decision=ReleaseDecision(
            verdict="risk",
            headline="⚠️ РЕЛИЗ С РИСКОМ",
            items=["test issue"],
        ),
        blockers=[],
        highs=[issue],
        test_unique_count=10,
        stage_unique_count=5,
        shared_count=2,
    )


def test_write_analyst_pdf(tmp_path: Path):
    if find_font_path() is None:
        pytest.skip("TTF font not available")
    path = tmp_path / "qa_report_2026-05-19.pdf"
    result = write_analyst_pdf(_minimal_report(), path)
    assert path.is_file()
    assert result.page_count >= 1
    assert result.highs == 1


def test_write_analyst_pdf_medium_low_table(tmp_path: Path):
    if find_font_path() is None:
        pytest.skip("TTF font not available")
    now = datetime.now(timezone.utc)

    def issue(i: int, count: int) -> IssueRecord:
        return IssueRecord(
            id=str(i),
            title=f"Ошибка модуля {i}: timeout при сохранении",
            level="error",
            count=count,
            last_seen=now,
            first_seen=now,
            culprit="",
        )

    report = AnalystReport(
        product_name="vetmanager-extjs",
        fetched_at=now,
        decision=ReleaseDecision(verdict="ok", headline="✅ РЕЛИЗ ОК", items=[]),
        mediums=[issue(1, 120), issue(2, 60)],
        lows=[issue(3, 15)],
    )
    path = tmp_path / "qa_medium_low.pdf"
    result = write_analyst_pdf(report, path)
    assert path.is_file()
    assert result.mediums == 2
    assert result.lows == 1
