from __future__ import annotations

import sys
from pathlib import Path

import structlog

from qa_release_bot.analyzer import Severity, analyze_issue
from qa_release_bot.compare import compare_environments
from qa_release_bot.config import (
    Settings,
    build_comparison_refs,
    load_report_config,
    report_fetch_options,
    report_limits,
    report_output_dir,
)
from qa_release_bot.export_paths import resolve_report_paths
from qa_release_bot.fetcher import fetch_all_issues
from qa_release_bot.grouper import dedupe_by_title, group_by_title
from qa_release_bot.normalizer import normalize_issues
from qa_release_bot.pdf_report import write_pdf_report
from qa_release_bot.report import AnalyzedIssue, ProductQAReport, print_qa_report
from qa_release_bot.taxonomy import IssueCategory

log = structlog.get_logger(__name__)


class QAReportRunner:
    """Загрузка конфига → Glitchtip → нормализация → сравнение → AI → отчёт."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._report_config = load_report_config()

    def run(self) -> list[ProductQAReport]:
        comparisons = build_comparison_refs(self._settings, self._report_config)
        if not comparisons:
            log.warning("no_comparisons_configured")
            return []

        query, stats_period = report_fetch_options(self._report_config)
        reports: list[ProductQAReport] = []

        for pair in comparisons:
            test_ref = pair["test"]
            stage_ref = pair["stage"]
            name = pair["name"]

            raw_test = fetch_all_issues(
                self._settings,
                [test_ref],
                query=query,
                stats_period=stats_period,
            )
            raw_stage = fetch_all_issues(
                self._settings,
                [stage_ref],
                query=query,
                stats_period=stats_period,
            )

            test_norm = normalize_issues(raw_test, environment="test")
            stage_norm = normalize_issues(raw_stage, environment="stage")

            test_deduped = dedupe_by_title(test_norm)
            stage_deduped = dedupe_by_title(stage_norm)

            comparison = compare_environments(
                test_deduped,
                stage_deduped,
                product_name=name,
                test_project=test_ref.slug,
                stage_project=stage_ref.slug,
            )

            only_stage_titles = {i.title for i in comparison.only_stage}
            analyzed: dict[str, AnalyzedIssue] = {}

            for issue in test_deduped + stage_deduped:
                if issue.title not in analyzed:
                    analyzed[issue.title] = AnalyzedIssue(
                        issue=issue,
                        analysis=analyze_issue(
                            issue,
                            only_in_stage=issue.title in only_stage_titles,
                        ),
                    )

            all_items = list(analyzed.values())

            release_blockers = [
                a
                for a in all_items
                if a.analysis.blocks_release or (
                    a.analysis.category == IssueCategory.PRODUCT
                    and a.analysis.severity == Severity.BLOCKER
                    and a.analysis.user_impact >= 4
                )
            ]
            release_blockers = _unique_analyzed(release_blockers)

            product_stage = [
                analyzed[i.title]
                for i in comparison.only_stage
                if analyzed[i.title].analysis.category == IssueCategory.PRODUCT
            ]
            product_stage = _unique_analyzed(product_stage)

            regressions = [
                a for a in all_items if a.analysis.regression and a.analysis.category == IssueCategory.PRODUCT
            ]
            regressions = _unique_analyzed(regressions)

            infra = [a for a in all_items if a.analysis.category == IssueCategory.INFRASTRUCTURE]
            noise = [a for a in all_items if a.analysis.category == IssueCategory.NOISE]

            reports.append(
                ProductQAReport(
                    comparison=comparison,
                    test_groups=group_by_title(test_norm),
                    stage_groups=group_by_title(stage_norm),
                    release_blockers=release_blockers,
                    product_new_in_stage=product_stage,
                    regressions=regressions,
                    infrastructure=sorted(infra, key=_sort_key)[:30],
                    noise=sorted(noise, key=_sort_key)[:20],
                    all_analyzed=all_items,
                    # legacy aliases for tests
                    critical=release_blockers,
                    new_in_stage=product_stage,
                )
            )

        return reports

    def run_and_export(
        self,
        *,
        output: str | None = None,
        output_dir: str | None = None,
        save_files: bool = True,
        print_console: bool = True,
    ) -> tuple[Path | None, Path | None]:
        reports = self.run()
        limits = report_limits(self._report_config)

        if print_console:
            print_qa_report(reports, limits=limits)

        txt_path: Path | None = None
        pdf_path: Path | None = None

        if save_files and reports:
            names = [r.comparison.product_name for r in reports]
            txt_path, pdf_path = resolve_report_paths(
                output=output,
                output_dir=output_dir or report_output_dir(self._report_config),
                product_names=names,
            )
            with txt_path.open("w", encoding="utf-8") as f:
                print_qa_report(reports, file=f, limits=limits)
            write_pdf_report(reports, pdf_path, limits=limits)
            print(f"Текст: {txt_path.resolve()}", file=sys.stderr)
            print(f"PDF:   {pdf_path.resolve()}", file=sys.stderr)

        return txt_path, pdf_path


def _sort_key(item: AnalyzedIssue) -> tuple:
    return (-item.analysis.user_impact, -item.issue.count)


def _unique_analyzed(items: list[AnalyzedIssue]) -> list[AnalyzedIssue]:
    seen: set[str] = set()
    result: list[AnalyzedIssue] = []
    for item in items:
        if item.issue.title in seen:
            continue
        seen.add(item.issue.title)
        result.append(item)
    order = {
        Severity.BLOCKER: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    return sorted(
        result,
        key=lambda x: (
            order.get(x.analysis.severity, 9),
            -x.analysis.user_impact,
            -x.issue.count,
        ),
    )
