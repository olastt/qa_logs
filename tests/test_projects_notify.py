from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from qa_release_bot.config import Settings, build_summary_ref, load_report_config
from qa_release_bot.notify_format import (
    format_release_notify,
    format_summary_notify,
    release_verdict_short,
)
import pytest

from qa_release_bot.projects import list_cli_projects, project_ids_for_command, surge_domain, validate_command_project
from qa_release_bot.release_decision import ReleaseDecision


def test_build_summary_ref_cli_alias():
    ref = build_summary_ref(Settings(), load_report_config(), name="webapps-widgets")
    assert ref["name"] == "selectel-webappswidgets-test"
    assert ref["instance"] == "selectel"
    assert ref["project"].slug == "webappswidgets-test"


def test_build_summary_ref_config_name_unchanged():
    ref = build_summary_ref(
        Settings(),
        load_report_config(),
        name="selectel-webappswidgets-test",
    )
    assert ref["name"] == "selectel-webappswidgets-test"


def test_summary_watchlist_count():
    from qa_release_bot.config import build_summary_refs

    refs = build_summary_refs(Settings(), load_report_config())
    assert len(refs) == 16


def test_release_comparisons_count():
    assert len(project_ids_for_command("release")) == 6


def test_list_cli_projects_total():
    projects = list_cli_projects()
    assert len(projects) == 22
    assert "vetmanager-extjs" in project_ids_for_command("release")
    assert "selectel-webappswidgets-test" in project_ids_for_command("summary")
    assert "hetzner-vetmanager-extjs-test" in project_ids_for_command("summary")


def test_validate_command_project_mismatch():
    with pytest.raises(ValueError, match="Проверить релиз"):
        validate_command_project("summary", "vetmanager-extjs")
    with pytest.raises(ValueError, match="Проверить релиз|только сводка"):
        validate_command_project("release", "webapps-widgets")


def test_surge_domain():
    assert surge_domain("vetmanager-extjs", "release") == "qa-extjs-release.surge.sh"
    assert surge_domain("webapps-widgets", "summary") == "qa-widgets-summary.surge.sh"
    assert (
        surge_domain("selectel-webappswidgets-test", "summary")
        != surge_domain("hetzner-webappswidgets-test", "summary")
    )
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
