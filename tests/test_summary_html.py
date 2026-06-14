from datetime import datetime, timezone

from qa_release_bot.html_report import build_summary_html_context, render_html
from qa_release_bot.release_decision import decide_summary
from qa_release_bot.summary_report import SummaryReport


def test_summary_html_no_release_verdict_or_diff():
    now = datetime.now(timezone.utc)
    report = SummaryReport(
        product_name="webapps-widgets-test",
        instance="selectel",
        project_slug="webappswidgets-test",
        fetched_at=now,
        decision=decide_summary([], []),
        total_unresolved=0,
    )
    ctx = build_summary_html_context(
        report, glitchtip_base_url="https://glitchtip.example"
    )
    html = render_html(ctx)
    assert "РЕЛИЗ ЗАПРЕЩЁН" not in html
    assert "РЕЛИЗ ОК" not in html
    assert "Главное" in html
    assert "Есть ли новые критичные ошибки?" in html
    assert "Что появилось сегодня?" in html
    assert "Что требует действия?" in html
    assert "Дифф test↔stage" not in html
    assert "Динамика" not in html
    assert "Топ-10 по кол-ву" in html
