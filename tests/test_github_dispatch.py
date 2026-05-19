from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from github_dispatch import ACTION_RELEASE, ACTION_SUMMARY, parse_command


def test_parse_command_summary():
    action, project, notify = parse_command("/qa summary webapps-widgets")
    assert action == ACTION_SUMMARY
    assert project == "webapps-widgets"
    assert notify is True


def test_parse_command_release_ru():
    action, project, _ = parse_command("релиз vetmanager-extjs")
    assert action == ACTION_RELEASE
    assert project == "vetmanager-extjs"


def test_parse_command_all():
    _, project, _ = parse_command("сводка all")
    assert project == "ВСЕ ПРОЕКТЫ"


def test_parse_command_too_short():
    with pytest.raises(ValueError):
        parse_command("summary")
