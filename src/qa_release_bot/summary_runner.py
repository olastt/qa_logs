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
from qa_release_bot.new_issues import find_new_issues_by_id
from qa_release_bot.noise_groups import group_noise_issues
from qa_release_bot.release_decision import decide_release, split_by_severity
from qa_release_bot.severity_rules import IssueSeverity
from qa_release_bot.snapshot_store import SnapshotStore
from qa_release_bot.html_report import (
    default_summary_html_path,
    format_html_message,
    write_summary_html,
)
from qa_release_bot.summary_report import SummaryReport, render_summary_markdown

log = structlog.get_logger(__name__)


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

        current_ids = {i.id for i in raw}
        disappeared_count = len(prev_ids - current_ids) if prev_ids else 0

        new_items = find_new_issues_by_id(
            raw, prev, environment=snap_env, last_deploy=deploy
        )
        self._snapshots.save(snap_env, raw)

        deduped, noise_groups = group_noise_issues(raw)
        by_sev = split_by_severity(deduped)
        decision = decide_release(
            by_sev[IssueSeverity.BLOCKER],
            by_sev[IssueSeverity.HIGH],
        )

        summary = SummaryReport(
            product_name=ref["name"],
            instance=ref["instance"],
            project_slug=project.slug,
            fetched_at=fetched_at,
            decision=decision,
            total_unresolved=len(raw),
            blockers=by_sev[IssueSeverity.BLOCKER][:max_detail],
            highs=by_sev[IssueSeverity.HIGH][:max_detail],
            mediums=by_sev[IssueSeverity.MEDIUM],
            lows=by_sev[IssueSeverity.LOW],
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
            )
            print(format_html_message(html_path), file=sys.stderr)

        if save_pdf:
            from qa_release_bot.analyst_pdf import format_summary_message
            from qa_release_bot.summary_pdf import default_summary_pdf_path, write_summary_pdf

            pdf_path = default_summary_pdf_path(out_dir, summary)
            pdf_result = write_summary_pdf(summary, pdf_path)
            print(format_summary_message(pdf_result), file=sys.stderr)

        return summary
