from __future__ import annotations

import structlog

from qa_release_bot.client import GlitchtipClient
from qa_release_bot.config import (
    Settings,
    api_client_options,
    instance_credentials,
    load_report_config,
)
from qa_release_bot.models import GlitchtipIssue, GlitchtipProjectRef

log = structlog.get_logger(__name__)


def fetch_all_issues(
    settings: Settings,
    projects: list[GlitchtipProjectRef],
    *,
    query: str = "is:unresolved",
    stats_period: str = "24h",
) -> list[GlitchtipIssue]:
    """Тянет unresolved issues по всем настроенным проектам."""
    by_instance: dict[str, list[GlitchtipProjectRef]] = {}
    for ref in projects:
        by_instance.setdefault(ref.instance, []).append(ref)

    all_issues: list[GlitchtipIssue] = []
    for instance, refs in by_instance.items():
        base_url, token = instance_credentials(settings, instance)
        if not base_url or not token:
            log.warning("skip_instance_missing_credentials", instance=instance)
            continue

        api_opts = api_client_options(load_report_config())
        with GlitchtipClient(base_url, token, options=api_opts) as client:
            for project in refs:
                try:
                    issues = client.list_issues(
                        project,
                        query=query,
                        stats_period=stats_period,
                    )
                    log.info(
                        "fetched_issues",
                        instance=instance,
                        project=project.slug,
                        count=len(issues),
                    )
                    all_issues.extend(issues)
                except Exception:
                    log.exception(
                        "fetch_failed",
                        instance=instance,
                        project=project.slug,
                    )
    return all_issues
