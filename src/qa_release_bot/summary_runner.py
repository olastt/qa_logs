from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from qa_release_bot.client import GlitchtipClient
from qa_release_bot.config import (
    Settings,
    api_client_options,
    build_summary_ref,
    instance_credentials,
    last_deploy_date,
    load_report_config,
    report_fetch_options,
    report_output_dir,
    snapshots_dir,
)
from qa_release_bot.new_issues import NewIssueItem, find_new_issues_first_seen_today
from qa_release_bot.noise_groups import group_noise_issues
from qa_release_bot.glitchtip_levels import split_by_glitchtip_level
from qa_release_bot.release_decision import decide_summary_by_level
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.snapshot_store import SnapshotStore
from qa_release_bot.html_report import (
    default_summary_html_path,
    format_html_message,
    write_summary_html,
)
from qa_release_bot.summary_report import SummaryReport, render_summary_markdown

log = structlog.get_logger(__name__)


def _merge_issue_records(
    primary: list[IssueRecord], secondary: list[IssueRecord]
) -> list[IssueRecord]:
    by_id: dict[str, IssueRecord] = {str(i.id): i for i in primary}
    for issue in secondary:
        key = str(issue.id)
        prev = by_id.get(key)
        if prev is None:
            by_id[key] = issue
            continue
        if len(issue.stack_frames) > len(prev.stack_frames):
            by_id[key] = issue
        elif issue.count > prev.count:
            by_id[key] = issue
    return list(by_id.values())


def _enrich_new_issue_items(
    items: list[NewIssueItem], enriched_pool: list[IssueRecord]
) -> list[NewIssueItem]:
    by_id = {str(i.id): i for i in enriched_pool}
    out: list[NewIssueItem] = []
    for item in items:
        issue = by_id.get(str(item.issue.id), item.issue)
        out.append(
            NewIssueItem(
                issue=issue,
                environment=item.environment,
                severity=item.severity,
                tracker_title=item.tracker_title,
                deploy_hint=item.deploy_hint,
            )
        )
    return out


class SingleProjectSummaryRunner:
    """Одна среда — сводка в консоль/markdown, без сравнения test↔stage."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._report_config = load_report_config()
        self._snapshots = SnapshotStore(Path(snapshots_dir(self._report_config)))

    def run(
        self,
        *,
        name: str | None = None,
        instance: str | None = None,
        project_slug: str | None = None,
        save_markdown: Path | None = None,
        save_html: bool = True,
        save_pdf: bool = False,
        print_console: bool = True,
        enrich_stack: bool | None = None,
    ) -> SummaryReport:
        ref = build_summary_ref(
            self._settings,
            self._report_config,
            name=name,
            instance=instance,
            project_slug=project_slug,
        )
        query, stats_period = report_fetch_options(self._report_config)
        deploy = last_deploy_date(self._report_config)
        limits = self._report_config.get("report_limits") or {}
        max_detail = int(limits.get("max_critical", 20))

        base_url, token = instance_credentials(self._settings, ref["instance"])
        fetched_at = datetime.now(timezone.utc)
        today = fetched_at.date()
        snap_env: str = ref["snapshot_env"]
        project = ref["project"]

        prev = self._snapshots.load_latest_before(snap_env, reference=today)
        is_first_run = prev is None
        prev_ids = set(prev.keys()) if prev else set()

        api_opts = api_client_options(self._report_config)
        if enrich_stack is False:
            from dataclasses import replace

            api_opts = replace(api_opts, enrich_stack=False)

        with GlitchtipClient(base_url, token, options=api_opts) as client:
            log.info("fetching_summary", instance=ref["instance"], project=project.slug)
            raw = client.fetch_issue_records(
                project, query=query, stats_period=stats_period
            )
            log.info("fetching_all_for_new_today", project=project.slug)
            all_for_new = _merge_issue_records(
                client.fetch_all_issue_records(project, query=None, stats_period="90d"),
                client.fetch_all_issue_records(
                    project, query=query, stats_period=stats_period
                ),
            )

        current_ids = {i.id for i in raw}
        disappeared_count = len(prev_ids - current_ids) if prev_ids else 0
        summary_project_id = next(
            (i.project_id for i in raw if i.project_id),
            next((i.project_id for i in all_for_new if i.project_id), ""),
        )

        new_items = find_new_issues_first_seen_today(
            all_for_new,
            reference_at=fetched_at,
            environment=snap_env,
            last_deploy=deploy,
            glitchtip_base_url=base_url.rstrip("/"),
            glitchtip_org_slug=self._settings.glitchtip_org_slug,
            glitchtip_project_id=summary_project_id,
        )
        new_items = _enrich_new_issue_items(new_items, raw)
        log.info("new_issues_today", count=len(new_items), project=project.slug)
        self._snapshots.save(snap_env, raw)

        deduped, noise_groups, noise_stats = group_noise_issues(raw)
        level_sections = split_by_glitchtip_level(deduped)
        product_count = sum(len(issues) for _, issues in level_sections)
        decision = decide_summary_by_level(level_sections)
        summary = SummaryReport(
            product_name=ref["name"],
            instance=ref["instance"],
            project_slug=project.slug,
            project_id=summary_project_id,
            fetched_at=fetched_at,
            decision=decision,
            total_unresolved=len(raw),
            product_issue_count=product_count,
            noise_excluded_count=noise_stats.noise_excluded,
            before_title_dedupe_count=noise_stats.before_title_dedupe,
            level_sections=level_sections,
            noise_groups=noise_groups,
            new_issues=new_items,
            disappeared_count=disappeared_count,
            is_first_run=is_first_run,
            stats_period=stats_period,
            issue_query=query,
        )

        md = render_summary_markdown(summary)
        if print_console:
            print(md)

        if save_markdown:
            save_markdown.parent.mkdir(parents=True, exist_ok=True)
            save_markdown.write_text(md, encoding="utf-8")
            print(f"Markdown: {save_markdown.resolve()}", file=sys.stderr)

        out_dir = Path(report_output_dir(self._report_config))
        if save_html:
            html_path = default_summary_html_path(out_dir, summary)
            write_summary_html(
                summary,
                html_path,
                store=self._snapshots,
                glitchtip_base_url=base_url,
                glitchtip_org_slug=self._settings.glitchtip_org_slug,
            )
            print(format_html_message(html_path), file=sys.stderr)

        if save_pdf:
            from qa_release_bot.analyst_pdf import format_summary_message
            from qa_release_bot.summary_pdf import default_summary_pdf_path, write_summary_pdf

            pdf_path = default_summary_pdf_path(out_dir, summary)
            pdf_result = write_summary_pdf(summary, pdf_path)
            print(format_summary_message(pdf_result), file=sys.stderr)

        return summary
