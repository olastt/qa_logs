from datetime import datetime, timezone

from qa_release_bot.html_dates import fmt_datetime_ru


def test_fmt_datetime_ru_includes_time():
    dt = datetime(2026, 5, 18, 17, 20, tzinfo=timezone.utc)
    assert fmt_datetime_ru(dt) == "18 мая в 17:20"
