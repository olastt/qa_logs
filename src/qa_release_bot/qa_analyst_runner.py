from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from qa_release_bot.client import GlitchtipClient
from qa_release_bot.config import (
    Settings,
    api_client_options,
    build_comparison_refs,
    instance_credentials,
    last_deploy_date,
    load_report_config,
    report_fetch_options,
    snapshots_dir,
    report_output_dir,
)
from qa_release_bot.markdown_report import AnalystReport, render_markdown
from qa_release_bot.html_report import (
    default_analyst_html_path,
    format_html_message,
    write_analyst_html,
)
from qa_release_bot.new_issues import find_new_issues_by_id
from qa_release_bot.noise_groups import _normalize_title, group_noise_issues
from qa_release_bot.regression_detect import find_regressions
from qa_release_bot.release_decision import decide_release, split_by_severity
from qa_release_bot.severity_rules import IssueSeverity
from qa_release_bot.snapshot_store import SnapshotStore
from qa_release_bot.trends import build_trends
from qa_release_bot.tuesday_diff import build_stage_diff

log = structlog.get_logger(__name__)


class QAAnalystRunner:
    """QA-аналитик vetmanager-extjs: Glitchtip → снапшоты → выводы без ручного разбора."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._report_config = load_report_config()
        self._snapshots = SnapshotStore(Path(snapshots_dir(self._report_config)))

    def run(
        self,
        *,
        project_name: str | None = None,
        save_markdown: Path | None = None,
        save_html: bool = True,
        save_pdf: bool = False,
        print_console: bool = True,
        enrich_stack: bool | None = None,
    ) -> AnalystReport:
        comparisons = build_comparison_refs(self._settings, self._report_config)
        if not comparisons:
            raise RuntimeError("Нет пар test/stage в config/report.yaml")

        if project_name:
            pair = next((c for c in comparisons if c["name"] == project_name), None)
            if pair is None:
                known = ", ".join(c["name"] for c in comparisons)
                raise ValueError(
                    f"Проект релиза «{project_name}» не найден. Доступны: {known}"
                )
        else:
            pair = comparisons[0]
        product = pair["name"]
        instance = pair["instance"]
        test_ref = pair["test"]
        stage_ref = pair["stage"]
        query, stats_period = report_fetch_options(self._report_config)
        deploy = last_deploy_date(self._report_config)

        base_url, token = instance_credentials(self._settings, instance)
        fetched_at = datetime.now(timezone.utc)
        today = fetched_at.date()

        prev_stage = self._snapshots.load_latest_before("stage", reference=today)
        prev_test = self._snapshots.load_latest_before("test", reference=today)
        prev_tuesday_stage = self._snapshots.load_previous_tuesday("stage", reference=today)
        is_first_run = prev_stage is None and prev_test is None

        api_opts = api_client_options(self._report_config)
        if enrich_stack is False:
            from dataclasses import replace

            api_opts = replace(api_opts, enrich_stack=False)
        with GlitchtipClient(base_url, token, options=api_opts) as client:
            log.info("fetching_test", project=test_ref.slug)
            test_raw = client.fetch_issue_records(
                test_ref, query=query, stats_period=stats_period
            )
            log.info("fetching_stage", project=stage_ref.slug)
            stage_raw = client.fetch_issue_records(
                stage_ref, query=query, stats_period=stats_period
            )

        new_stage = find_new_issues_by_id(stage_raw, prev_stage, environment="stage", last_deploy=deploy)
        new_test = find_new_issues_by_id(test_raw, prev_test, environment="test", last_deploy=deploy)

        self._snapshots.save("test", test_raw)
        self._snapshots.save("stage", stage_raw)

        test_deduped, _ = group_noise_issues(test_raw)
        stage_deduped, noise_groups = group_noise_issues(stage_raw)

        diff_rows = build_stage_diff(stage_deduped, prev_tuesday_stage)
        diff_available = prev_tuesday_stage is not None

        regressions = find_regressions(
            stage_deduped,
            test_deduped,
            last_deploy=deploy,
            diff_rows=diff_rows,
        )

        by_sev = split_by_severity(stage_deduped)
        decision = decide_release(
            by_sev[IssueSeverity.BLOCKER],
            by_sev[IssueSeverity.HIGH],
        )
        trends = build_trends(self._snapshots, "stage", weeks=4)

        test_keys = {_normalize_title(i.title) for i in test_deduped}
        stage_keys = {_normalize_title(i.title) for i in stage_deduped}

        analyst_report = AnalystReport(
            product_name=product,
            fetched_at=fetched_at,
            decision=decision,
            blockers=by_sev[IssueSeverity.BLOCKER],
            highs=by_sev[IssueSeverity.HIGH],
            mediums=by_sev[IssueSeverity.MEDIUM],
            lows=by_sev[IssueSeverity.LOW],
            diff_rows=diff_rows,
            regressions=regressions,
            noise_groups=noise_groups,
            trends=trends,
            diff_available=diff_available,
            test_unique_count=len(test_keys),
            stage_unique_count=len(stage_keys),
            shared_count=len(test_keys & stage_keys),
            new_issues_stage=new_stage,
            new_issues_test=new_test,
            is_first_run=is_first_run,
            is_tuesday_diff=diff_available,
            stats_period=stats_period,
            issue_query=query,
        )

        md = render_markdown(analyst_report)
        if print_console:
            print(md)

        if save_markdown:
            save_markdown.parent.mkdir(parents=True, exist_ok=True)
            save_markdown.write_text(md, encoding="utf-8")
            print(f"Markdown: {save_markdown.resolve()}", file=sys.stderr)

        out_dir = Path(report_output_dir(self._report_config))
        if save_html:
            html_path = default_analyst_html_path(out_dir, fetched_at)
            write_analyst_html(
                analyst_report,
                html_path,
                store=self._snapshots,
                glitchtip_base_url=base_url,
            )
            print(format_html_message(html_path), file=sys.stderr)

        if save_pdf:
            from qa_release_bot.analyst_pdf import (
                default_pdf_path,
                format_summary_message,
                write_analyst_pdf,
            )

            pdf_path = default_pdf_path(out_dir, fetched_at)
            pdf_result = write_analyst_pdf(analyst_report, pdf_path)
            print(format_summary_message(pdf_result), file=sys.stderr)

        return analyst_report
