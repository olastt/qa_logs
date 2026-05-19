from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from qa_release_bot.models import GlitchtipProjectRef


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    glitchtip_org_slug: str = Field(default="vetmanager", alias="GLITCHTIP_ORG_SLUG")
    poll_interval_sec: int = Field(default=300, alias="POLL_INTERVAL_SEC")
    state_db_path: Path = Field(default=Path("data/state.db"), alias="STATE_DB_PATH")

    glitchtip_hetzner_url: str = Field(default="", alias="GLITCHTIP_HETZNER_URL")
    glitchtip_hetzner_token: str = Field(default="", alias="GLITCHTIP_HETZNER_TOKEN")
    glitchtip_selectel_url: str = Field(default="", alias="GLITCHTIP_SELECTEL_URL")
    glitchtip_selectel_token: str = Field(default="", alias="GLITCHTIP_SELECTEL_TOKEN")

    @field_validator(
        "glitchtip_org_slug",
        "glitchtip_hetzner_url",
        "glitchtip_hetzner_token",
        "glitchtip_selectel_url",
        "glitchtip_selectel_token",
        mode="before",
    )
    @classmethod
    def _strip_env_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("glitchtip_org_slug", mode="after")
    @classmethod
    def _org_slug_default(cls, value: str) -> str:
        return value or "vetmanager"


def load_instances_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path(__file__).resolve().parents[2] / "config" / "instances.yaml"
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_project_refs(
    settings: Settings,
    instances_config: dict[str, Any] | None = None,
) -> list[GlitchtipProjectRef]:
    """Собирает список проектов для опроса из YAML + env."""
    raw = instances_config or load_instances_config()
    env_map = {
        "GLITCHTIP_HETZNER_URL": settings.glitchtip_hetzner_url,
        "GLITCHTIP_HETZNER_TOKEN": settings.glitchtip_hetzner_token,
        "GLITCHTIP_SELECTEL_URL": settings.glitchtip_selectel_url,
        "GLITCHTIP_SELECTEL_TOKEN": settings.glitchtip_selectel_token,
    }

    refs: list[GlitchtipProjectRef] = []
    for instance_name, instance_cfg in raw.get("instances", {}).items():
        url_env = instance_cfg["base_url_env"]
        token_env = instance_cfg["token_env"]
        if not env_map.get(url_env) or not env_map.get(token_env):
            continue

        for project in instance_cfg.get("projects", []):
            refs.append(
                GlitchtipProjectRef(
                    instance=instance_name,
                    org_slug=settings.glitchtip_org_slug,
                    slug=project["slug"],
                    label=project.get("label"),
                )
            )
    return refs


def instance_credentials(settings: Settings, instance: str) -> tuple[str, str]:
    if instance == "hetzner":
        return (
            settings.glitchtip_hetzner_url.strip().rstrip("/"),
            settings.glitchtip_hetzner_token.strip(),
        )
    if instance == "selectel":
        return (
            settings.glitchtip_selectel_url.strip().rstrip("/"),
            settings.glitchtip_selectel_token.strip(),
        )
    raise ValueError(f"Unknown instance: {instance}")


def _resolve_summary_config_name(name: str, raw: dict[str, Any]) -> str:
    """CLI id → имя сводки в config (только прямое сопоставление)."""
    aliases: dict[str, str] = dict(raw.get("cli_aliases") or {})
    return aliases.get(name, name)


def load_report_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path(__file__).resolve().parents[2] / "config" / "report.yaml"
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_comparison_refs(
    settings: Settings,
    report_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Пары test/stage из config/report.yaml."""
    raw = report_config or load_report_config()
    refs: list[dict[str, Any]] = []
    for item in raw.get("comparisons", []):
        instance = item["instance"]
        refs.append(
            {
                "name": item["name"],
                "instance": instance,
                "test": GlitchtipProjectRef(
                    instance=instance,
                    org_slug=settings.glitchtip_org_slug,
                    slug=item["test_slug"],
                ),
                "stage": GlitchtipProjectRef(
                    instance=instance,
                    org_slug=settings.glitchtip_org_slug,
                    slug=item["stage_slug"],
                ),
            }
        )
    return refs


def _summary_entry(
    settings: Settings,
    *,
    name: str,
    instance: str,
    slug: str,
    label: str | None = None,
    snapshot_env: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "instance": instance,
        "project": GlitchtipProjectRef(
            instance=instance,
            org_slug=settings.glitchtip_org_slug,
            slug=slug,
            label=label,
        ),
        "snapshot_env": snapshot_env or slug,
    }


def build_summary_refs(
    settings: Settings,
    report_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Сводки: summaries + summary_watchlist (slug из instances.yaml)."""
    raw = report_config or load_report_config()
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(entry: dict[str, Any]) -> None:
        if entry["name"] in seen:
            return
        seen.add(entry["name"])
        refs.append(entry)

    for item in raw.get("summaries", []):
        instance = item["instance"]
        slug = item["project_slug"]
        add(
            _summary_entry(
                settings,
                name=item["name"],
                instance=instance,
                slug=slug,
                label=item.get("label"),
                snapshot_env=item.get("snapshot_env"),
            )
        )

    watchlist: dict[str, list[Any]] = raw.get("summary_watchlist") or {}
    if watchlist:
        instances_cfg = load_instances_config().get("instances", {})
        for instance, slugs in watchlist.items():
            projects_by_slug = {
                p["slug"]: p
                for p in instances_cfg.get(instance, {}).get("projects", [])
            }
            for item in slugs:
                if isinstance(item, dict):
                    slug = item["slug"]
                    label = item.get("label")
                else:
                    slug = str(item)
                    label = projects_by_slug.get(slug, {}).get("label")
                if slug not in projects_by_slug and label is None:
                    label = None
                name = f"{instance}-{slug}"
                add(
                    _summary_entry(
                        settings,
                        name=name,
                        instance=instance,
                        slug=slug,
                        label=label,
                        snapshot_env=name,
                    )
                )

    return refs


def build_summary_ref(
    settings: Settings,
    report_config: dict[str, Any] | None = None,
    *,
    name: str | None = None,
    instance: str | None = None,
    project_slug: str | None = None,
) -> dict[str, Any]:
    """Один проект: из CLI-флагов или первый/именованный из summaries."""
    refs = build_summary_refs(settings, report_config)

    if instance and project_slug:
        for r in refs:
            if r["instance"] == instance and r["project"].slug == project_slug:
                return r
        return {
            "name": name or project_slug,
            "instance": instance,
            "project": GlitchtipProjectRef(
                instance=instance,
                org_slug=settings.glitchtip_org_slug,
                slug=project_slug,
            ),
            "snapshot_env": project_slug,
        }

    if name:
        cfg = report_config or load_report_config()
        resolved = _resolve_summary_config_name(name, cfg)
        for r in refs:
            if r["name"] == resolved:
                return r
        raise ValueError(f"Сводка '{name}' не найдена в config/report.yaml → summaries")

    if refs:
        return refs[0]

    raise RuntimeError(
        "Нет summaries в config/report.yaml. "
        "Добавьте блок summaries или: "
        "qa-release-bot summary --instance selectel --project webappswidgets-test"
    )


def report_fetch_options(report_config: dict[str, Any] | None = None) -> tuple[str, str]:
    raw = report_config or load_report_config()
    return raw.get("issue_query", "is:unresolved"), raw.get("stats_period", "14d")


def report_limits(report_config: dict[str, Any] | None = None) -> dict[str, int]:
    raw = report_config or load_report_config()
    defaults = {
        "max_critical": 20,
        "max_new_in_stage": 20,
        "max_regressions": 20,
        "max_env_only_list": 30,
        "title_max_len": 90,
    }
    defaults.update(raw.get("report_limits") or {})
    return defaults


def report_output_dir(report_config: dict[str, Any] | None = None) -> str:
    raw = report_config or load_report_config()
    return raw.get("output_dir", "reports")


def snapshots_dir(report_config: dict[str, Any] | None = None) -> str:
    raw = report_config or load_report_config()
    return raw.get("snapshots_dir", "snapshots")


def api_client_options(report_config: dict[str, Any] | None = None):
    from qa_release_bot.client import ApiClientOptions

    raw = report_config or load_report_config()
    api = raw.get("api") or {}
    return ApiClientOptions(
        max_retries=int(api.get("max_retries", 6)),
        retry_base_sec=float(api.get("retry_base_sec", 2.0)),
        delay_between_requests_sec=float(api.get("delay_between_requests_sec", 0.5)),
        enrich_stack=bool(api.get("enrich_stack", True)),
        enrich_stack_max_issues=int(api.get("enrich_stack_max_issues", 30)),
        enrich_stack_delay_sec=float(api.get("enrich_stack_delay_sec", 0.25)),
    )


def last_deploy_date(report_config: dict[str, Any] | None = None) -> date | None:
    from datetime import date as date_cls

    raw = report_config or load_report_config()
    value = raw.get("last_deploy_date")
    if not value:
        return None
    return date_cls.fromisoformat(str(value))
