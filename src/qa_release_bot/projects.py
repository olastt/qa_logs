"""CLI-проекты: release и summary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qa_release_bot.config import (
    Settings,
    _resolve_summary_config_name,
    build_summary_refs,
    load_report_config,
)

ALL_PROJECTS_LABEL = "ВСЕ ПРОЕКТЫ"


@dataclass(frozen=True, slots=True)
class CliProject:
    id: str
    kind: str  # release | summary
    summary_config_name: str | None = None
    title: str = ""


def list_cli_projects() -> list[CliProject]:
    cfg = load_report_config()
    by_id: dict[str, CliProject] = {}

    for item in cfg.get("comparisons", []):
        pid = item["name"]
        by_id[pid] = CliProject(
            id=pid,
            kind="release",
            title=f"Релиз {pid} (test + stage)",
        )

    settings = Settings()
    for ref in build_summary_refs(settings, cfg):
        config_name = ref["name"]
        label = ref["project"].label or ref["project"].slug
        pid = _summary_cli_id(config_name, cfg)
        by_id[pid] = CliProject(
            id=pid,
            kind="summary",
            summary_config_name=config_name,
            title=f"Сводка {label} ({ref['instance']})",
        )

    for pid, meta in (cfg.get("cli_projects") or {}).items():
        kind = meta.get("kind", "summary")
        if kind == "release":
            by_id[pid] = CliProject(id=pid, kind="release", title=f"Релиз {pid}")
        else:
            by_id[pid] = CliProject(
                id=pid,
                kind="summary",
                summary_config_name=meta.get("summary_name", pid),
                title=f"Сводка {pid}",
            )

    return sorted(by_id.values(), key=lambda p: p.id)


def get_cli_project(project_id: str) -> CliProject:
    cfg = load_report_config()
    config_name = _resolve_summary_config_name(project_id, cfg)
    for p in list_cli_projects():
        if p.id == project_id or p.summary_config_name == config_name:
            return p
    known = ", ".join(p.id for p in list_cli_projects())
    raise ValueError(f"Неизвестный проект «{project_id}». Доступны: {known}")


def project_ids_for_command(command: str) -> list[str]:
    return [p.id for p in list_cli_projects() if p.kind == command]


def validate_command_project(command: str, project_id: str) -> None:
    """Проверка пары команда + проект (release/summary)."""
    project = get_cli_project(project_id)
    if project.kind == command:
        return

    release_ids = ", ".join(project_ids_for_command("release")) or "—"
    summary_ids = ", ".join(project_ids_for_command("summary")) or "—"

    if command == "summary":
        raise ValueError(
            f"«{project_id}» — это проверка релиза (test + stage), не сводка.\n"
            f"Для сводки выберите проект: {summary_ids}\n"
            f"Для {project_id} в Actions выберите: 🚦 Проверить релиз"
        )
    raise ValueError(
        f"«{project_id}» — только сводка по одной среде, без test/stage.\n"
        f"Для релиза выберите проект: {release_ids}\n"
        f"Для {project_id} в Actions выберите: 📊 Сводка — что нового"
    )


def all_cli_project_ids() -> list[str]:
    return [p.id for p in list_cli_projects()]


def surge_domain(project_id: str, command: str) -> str:
    """qa-extjs-release.surge.sh ← vetmanager-extjs / selectel-webappswidgets-test."""
    slug = project_id
    for prefix in ("selectel-", "hetzner-"):
        if slug.startswith(prefix):
            slug = slug[len(prefix) :]
            break
    slug = (
        slug.removeprefix("vetmanager-")
        .removeprefix("webappswidgets-")
        .replace("webapps-widgets-", "widgets-")
        .removeprefix("webapps-")
    )
    slug = slug.strip("-") or "logs"
    if len(slug) > 40:
        slug = slug[:40].rstrip("-")
    return f"qa-{slug}-{command}.surge.sh"


def _summary_cli_id(config_name: str, cfg: dict[str, Any]) -> str:
    aliases: dict[str, str] = dict(cfg.get("cli_aliases") or {})
    for pid, target in aliases.items():
        if target == config_name:
            return pid
    # selectel-*/hetzner-* — полный id, иначе test/stage/production путаются
    if config_name.startswith(("selectel-", "hetzner-")):
        return config_name
    if config_name.endswith("-test"):
        return config_name[: -len("-test")]
    return config_name
