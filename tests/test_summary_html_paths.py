from __future__ import annotations

from datetime import datetime, timezone

from qa_release_bot.html_report import default_summary_html_path
from qa_release_bot.release_decision import ReleaseDecision
from qa_release_bot.summary_report import SummaryReport


def _summary(instance: str) -> SummaryReport:
    return SummaryReport(
        product_name="webappswidgets-test",
        instance=instance,
        project_slug="webappswidgets-test",
        fetched_at=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc),
        decision=ReleaseDecision(verdict="ok", headline="", items=[]),
        total_unresolved=0,
    )


def test_summary_html_path_includes_instance(tmp_path):
    selectel = default_summary_html_path(tmp_path, _summary("selectel"))
    hetzner = default_summary_html_path(tmp_path, _summary("hetzner"))

    assert selectel.name == "summary_selectel_webappswidgets-test_2026-06-18.html"
    assert hetzner.name == "summary_hetzner_webappswidgets-test_2026-06-18.html"
    assert selectel != hetzner
