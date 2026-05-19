from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from qa_release_bot.issue_record import IssueRecord


@dataclass(slots=True)
class ModuleResolution:
    short_tag: str
    human_module: str | None
    controller_key: str | None
    is_mapped: bool


def load_module_map(path: Path | None = None) -> dict[str, str]:
    config_path = path or Path(__file__).resolve().parents[2] / "config" / "module_map.yaml"
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return dict(data.get("modules", {}))


def resolve_module(
    issue: IssueRecord,
    module_map: dict[str, str] | None = None,
) -> ModuleResolution:
    """Человекочитаемый модуль + короткий тег для названий и группировки."""
    mapping = module_map or load_module_map()
    controller = _find_controller_key(issue)

    if controller and controller in mapping:
        human = mapping[controller]
        return ModuleResolution(
            short_tag=_tag_from_human(human),
            human_module=human,
            controller_key=controller,
            is_mapped=True,
        )

    for key in sorted(mapping, key=len, reverse=True):
        if _key_in_issue(key, issue):
            human = mapping[key]
            return ModuleResolution(
                short_tag=_tag_from_human(human),
                human_module=human,
                controller_key=controller,
                is_mapped=True,
            )

    if controller:
        return ModuleResolution(
            short_tag=_tag_from_controller(controller),
            human_module=None,
            controller_key=controller,
            is_mapped=False,
        )

    return ModuleResolution(
        short_tag="ExtJS",
        human_module=None,
        controller_key=None,
        is_mapped=True,
    )


def _find_controller_key(issue: IssueRecord) -> str | None:
    for frame in issue.stack_frames:
        fn = frame.function or ""
        if "Controller" in fn:
            return fn.split("::")[0]
        if frame.filename:
            base = Path(frame.filename).stem
            if "Controller" in base:
                return base
    if issue.culprit:
        for part in issue.culprit.replace("\\", "/").split("/"):
            if "Controller" in part:
                return part.split(".php")[0].split("/")[-1]
    m = re.search(r"([A-Za-z0-9]+Controller)", issue.title)
    if m:
        return m.group(1)
    return None


def _key_in_issue(key: str, issue: IssueRecord) -> bool:
    blob = " ".join(
        [
            issue.title,
            issue.culprit,
            " ".join(f.function or "" for f in issue.stack_frames),
            " ".join(f.filename or "" for f in issue.stack_frames),
        ]
    ).lower()
    k = key.lower().replace("::", "")
    return key.lower() in blob or k in blob


def _tag_from_human(human: str) -> str:
    if "—" in human:
        return human.split("—")[0].strip()[:24]
    if "(" in human:
        return human.split("(")[0].strip()[:24]
    return human[:24]


def _tag_from_controller(controller: str) -> str:
    m = re.match(r"(Frame\d+)", controller)
    if m:
        return m.group(1)
    name = controller.replace("Controller", "")
    if name in ("Widget", "Dashly", "Reviews"):
        return name
    if "Admission" in name:
        return "Приёмы"
    if "Client" in name:
        return "Клиенты"
    return name[:20] or "ExtJS"


def collect_unmapped_controllers(
    issues: list[IssueRecord],
    module_map: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Список (ControllerName, предложение описания) для блока в конце отчёта."""
    mapping = module_map or load_module_map()
    seen: dict[str, str] = {}
    for issue in issues:
        res = resolve_module(issue, mapping)
        if res.controller_key and not res.is_mapped and res.controller_key not in seen:
            seen[res.controller_key] = _suggest_map_description(res.controller_key)
    return sorted(seen.items())


def _suggest_map_description(controller: str) -> str:
    area = controller.replace("Controller", "")
    if area.startswith("Frame"):
        return "раздел ExtJS (Frame)"
    if "Admission" in area:
        return "модуль приёмов"
    if "Client" in area:
        return "модуль клиентов"
    if "Widget" in area:
        return "виджеты"
    if "Dashly" in area:
        return "интеграция Dashly"
    if "Reviews" in area:
        return "отзывы"
    return "добавить в module_map.yaml"
