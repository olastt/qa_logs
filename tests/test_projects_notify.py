from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from qa_release_bot.notify_format import (
    format_release_notify,
    format_summary_notify,
    release_verdict_short,
)
from qa_release_bot.projects import surge_domain
from qa_release_bot.release_decision import ReleaseDecision


def test_surge_domain():
    assert surge_domain("vetmanager-extjs", "release") == "qa-extjs-release.surge.sh"
    assert surge_domain("webapps-widgets", "summary") == "qa-widgets-summary.surge.sh"
    assert surge_domain("vetmanager-laravel", "summary") == "qa-laravel-summary.surge.sh"


def test_release_verdict_short():
    assert release_verdict_short("forbidden") == "ЗАПРЕЩЁН"
    assert release_verdict_short("risk") == "С РИСКОМ"
    assert release_verdict_short("ok") == "ОК"


def test_format_release_notify():
    report = MagicMock()
    report.decision = ReleaseDecision(verdict="forbidden", headline="", items=[])
    report.blockers = [1, 2, 3]
    report.highs = [1, 2]
    text = format_release_notify(
        "vetmanager-extjs",
        report,
        "https://qa-extjs-release.surge.sh",
    )
    assert "🚦 Релиз vetmanager-extjs — ЗАПРЕЩЁН" in text
    assert "Блокеры: 3" in text
    assert "qa-extjs-release.surge.sh" in text


def test_format_summary_notify():
    summary = MagicMock()
    summary.new_issues = [1, 2, 3, 4, 5]
    text = format_summary_notify(
        "webapps-widgets",
        summary,
        disappeared_count=2,
        report_url="https://qa-widgets-summary.surge.sh",
    )
    assert "📊 Сводка webapps-widgets — готова" in text
    assert "Новых ошибок: 5" in text
    assert "Исчезло: 2" in text
