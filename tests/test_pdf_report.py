from datetime import datetime, timezone
from pathlib import Path

import pytest

from qa_release_bot.compare import compare_environments
from qa_release_bot.models import NormalizedIssue
from qa_release_bot.pdf_report import _find_font_path, write_pdf_report
from qa_release_bot.report import ProductQAReport


def _issue(iid: str, title: str, env: str) -> NormalizedIssue:
    now = datetime.now(timezone.utc)
    return NormalizedIssue(
        id=iid,
        short_id=iid,
        title=title,
        level="error",
        count=5,
        last_seen=now,
        stack_trace="Error: test\n  at fn (a.php)",
        environment=env,
        project_slug="p-test",
        instance="hetzner",
    )


@pytest.fixture
def sample_report() -> ProductQAReport:
    test = [_issue("1", "Error A", "test")]
    stage = [_issue("2", "Error B", "stage")]
    cmp = compare_environments(
        test,
        stage,
        product_name="demo",
        test_project="demo-test",
        stage_project="demo-stage",
    )
    return ProductQAReport(comparison=cmp)


def test_write_pdf_report(tmp_path: Path, sample_report: ProductQAReport):
    if _find_font_path() is None:
        pytest.skip("TTF font not available")
    pdf = tmp_path / "report.pdf"
    write_pdf_report([sample_report], pdf)
    assert pdf.is_file()
    assert pdf.stat().st_size > 500
