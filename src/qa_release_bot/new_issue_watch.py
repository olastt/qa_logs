from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qa_release_bot.client import GlitchtipClient
from qa_release_bot.config import (
    Settings,
    api_client_options,
    build_summary_ref,
    instance_credentials,
    load_report_config,
    report_fetch_options,
)
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.issue_titles import glitchtip_issue_url
from qa_release_bot.storage import IssueStateStore


@dataclass(slots=True)
class WatchedNewIssue:
    instance: str
    project_name: str
    issue: IssueRecord
    glitchtip_base_url: str


@dataclass(slots=True)
class WatchResult:
    alerts: list[WatchedNewIssue]
    checked_projects: int
    baseline_created: bool = False


def watch_new_issues(
    settings: Settings,
    project_ids: list[str],
    *,
    state_db_path: Path | None = None,
    baseline_on_first_run: bool = True,
    reference_at: datetime | None = None,
) -> WatchResult:
    cfg = load_report_config()
    query, stats_period = report_fetch_options(cfg)
    store = IssueStateStore(state_db_path or settings.state_db_path)
    baseline = baseline_on_first_run and store.watched_issue_count() == 0
    today_msk = _msk_date(reference_at or datetime.now(timezone.utc))

    alerts: list[WatchedNewIssue] = []
    refs = [build_summary_ref(settings, cfg, name=pid) for pid in project_ids]
    for ref in refs:
        project = ref["project"]
        base_url, token = instance_credentials(settings, ref["instance"])
        with GlitchtipClient(base_url, token, options=api_client_options(cfg)) as client:
            issues = client.fetch_issue_records(
                project,
                query=query,
                stats_period=stats_period,
                limit=100,
                enrich_stack=False,
            )
        for issue in issues:
            if store.is_watched_issue_known(ref["instance"], project.slug, issue.id):
                store.mark_watched_issue_seen(ref["instance"], project.slug, issue.id)
                continue
            if not baseline and _msk_date(issue.first_seen) == today_msk:
                alerts.append(
                    WatchedNewIssue(
                        instance=ref["instance"],
                        project_name=project.label or ref["name"],
                        issue=issue,
                        glitchtip_base_url=base_url,
                    )
                )
            store.mark_watched_issue_seen(ref["instance"], project.slug, issue.id)

    alerts.sort(key=lambda item: (item.project_name, item.issue.first_seen, item.issue.id))
    return WatchResult(alerts=alerts, checked_projects=len(refs), baseline_created=baseline)


def format_new_issue_watch_notify(result: WatchResult, *, max_items: int = 10) -> str:
    detected_at = datetime.now(timezone.utc)
    if result.baseline_created:
        return (
            "QA Bot: наблюдение за новыми ошибками включено\n"
            f"Проверено проектов: {result.checked_projects}\n"
            "Текущие ошибки запомнены как baseline, уведомления по ним не отправлялись."
        )
    if not result.alerts:
        return (
            "QA Bot: совершенно новых ошибок в Glitchtip нет\n"
            f"Проверено проектов: {result.checked_projects}"
        )

    lines = [
        f"🆕 QA Bot: новые ошибки в Glitchtip — {len(result.alerts)}",
        f"Проверено проектов: {result.checked_projects}",
    ]
    for item in result.alerts[:max_items]:
        issue = item.issue
        lines.append("")
        lines.append(f"Проект: [{item.instance}] {item.project_name}")
        lines.append(f"Уровень: {issue.level.upper()} · повторов: {issue.count}")
        lines.append(f"Ошибка: {_short(issue.title, 220)}")
        lines.append(f"Первое появление в Glitchtip: {_format_msk(issue.first_seen)}")
        lines.append(f"Обнаружено ботом: {_format_msk(detected_at)}")
        url = glitchtip_issue_url(
            item.glitchtip_base_url,
            issue.id,
            issue.org_slug,
            issue.project_id,
        )
        if url:
            lines.append(f"Ссылка: {url}")
    if len(result.alerts) > max_items:
        lines.append("")
        lines.append(f"...и ещё {len(result.alerts) - max_items}")
    return "\n".join(lines)


def _short(value: str, max_len: int) -> str:
    value = " ".join(value.split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "..."


def _format_msk(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(timezone(timedelta(hours=3)))
    return local.strftime("%Y-%m-%d %H:%M МСК")


def _msk_date(value: datetime):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=3))).date()
