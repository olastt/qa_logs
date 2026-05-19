from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from qa_release_bot.analyzer import IssueAnalysis, Severity
from qa_release_bot.compare import EnvironmentComparison
from qa_release_bot.grouper import group_by_title
from qa_release_bot.models import NormalizedIssue, TitleGroup
from qa_release_bot.taxonomy import (
    IssueCategory,
    category_label,
    cluster_label,
)
from qa_release_bot.textfmt import compact_text, wrap_text

_DEFAULT_LIMITS = {
    "max_critical": 20,
    "max_new_in_stage": 20,
    "max_regressions": 20,
    "max_env_only_list": 30,
    "max_infra": 15,
    "max_noise": 10,
    "title_max_len": 90,
}

_SEVERITY_ORDER = {
    Severity.BLOCKER: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


@dataclass(slots=True)
class AnalyzedIssue:
    issue: NormalizedIssue
    analysis: IssueAnalysis


@dataclass(slots=True)
class ProductQAReport:
    comparison: EnvironmentComparison
    test_groups: list[TitleGroup] = field(default_factory=list)
    stage_groups: list[TitleGroup] = field(default_factory=list)
    release_blockers: list[AnalyzedIssue] = field(default_factory=list)
    product_new_in_stage: list[AnalyzedIssue] = field(default_factory=list)
    regressions: list[AnalyzedIssue] = field(default_factory=list)
    infrastructure: list[AnalyzedIssue] = field(default_factory=list)
    noise: list[AnalyzedIssue] = field(default_factory=list)
    all_analyzed: list[AnalyzedIssue] = field(default_factory=list)
    # обратная совместимость
    critical: list[AnalyzedIssue] = field(default_factory=list)
    new_in_stage: list[AnalyzedIssue] = field(default_factory=list)


def print_qa_report(
    reports: list[ProductQAReport],
    *,
    file=None,
    limits: dict[str, int] | None = None,
) -> None:
    """Печатает QA-отчёт с release risk (продукт / инфра / шум)."""
    out = file or sys.stdout
    lim = {**_DEFAULT_LIMITS, **(limits or {})}
    title_max = lim["title_max_len"]
    width = 72

    _line(out, "=", width)
    _center(out, "QA RELEASE REPORT — Glitchtip", width)
    _line(out, "=", width)
    _writeln(out, f"Сформирован: {_format_dt(datetime.now())}")
    _writeln(out, "Модель: release risk (не «всё из Sentry = блокер»)")
    _writeln(out, "")

    if not reports:
        _writeln(out, "Нет данных для отчёта. Проверьте .env и config/report.yaml.")
        return

    for report in reports:
        _print_product_report(report, out=out, width=width, limits=lim, title_max=title_max)

    _line(out, "=", width)
    _center(out, "Конец отчёта", width)
    _line(out, "=", width)


def _print_product_report(
    report: ProductQAReport,
    *,
    out,
    width: int,
    limits: dict[str, int],
    title_max: int,
) -> None:
    cmp = report.comparison
    _line(out, "-", width)
    _writeln(out, f"Продукт: {cmp.product_name}")
    _writeln(out, f"  TEST  → {cmp.test_project}")
    _writeln(out, f"  STAGE → {cmp.stage_project}")
    _writeln(out, "")

    _section(out, "1. Сводка и Release Risk Score")
    _print_category_summary(out, report)
    _print_risk_score(out, report)
    _note_api_limit(out, cmp)
    _writeln(out, "")

    _section(out, "2. Кластеры причин (продуктовые ошибки)")
    _print_cluster_summary(out, report)
    _writeln(out, "")

    _print_analyzed_section(
        out,
        "3. BLOCKER — стоп релиза (только продукт, impact ≥ 4)",
        report.release_blockers,
        limits["max_critical"],
        title_max,
    )
    _print_analyzed_section(
        out,
        "4. Продуктовые баги только на STAGE",
        report.product_new_in_stage,
        limits["max_new_in_stage"],
        title_max,
    )
    _print_analyzed_section(
        out,
        "5. Регрессии (продукт, stage без test)",
        report.regressions,
        limits["max_regressions"],
        title_max,
    )
    _print_analyzed_section(
        out,
        "6. Инфра / интеграции (информационно, не стоп релиза)",
        report.infrastructure,
        limits.get("max_infra", 15),
        title_max,
        compact=True,
    )
    _print_analyzed_section(
        out,
        "7. Шум / warnings (низкий приоритет)",
        report.noise,
        limits.get("max_noise", 10),
        title_max,
        compact=True,
    )

    _section(out, "8. Дубликаты по title")
    _writeln(out, "  --- TEST ---")
    _print_duplicate_groups(report.test_groups, out, title_max=title_max)
    _writeln(out, "  --- STAGE ---")
    _print_duplicate_groups(report.stage_groups, out, title_max=title_max)
    _writeln(out, "")

    _print_env_only_section(
        out,
        "9. Только в TEST (с меткой категории)",
        cmp.only_test,
        report,
        limits["max_env_only_list"],
        title_max,
    )
    _print_env_only_section(
        out,
        "10. Только в STAGE (с меткой категории)",
        cmp.only_stage,
        report,
        limits["max_env_only_list"],
        title_max,
    )


def _print_category_summary(out, report: ProductQAReport) -> None:
    cmp = report.comparison
    by_env: dict[str, Counter] = {"test": Counter(), "stage": Counter()}
    title_to_cat: dict[str, IssueCategory] = {
        a.issue.title: a.analysis.category for a in report.all_analyzed
    }
    for issue in cmp.test_issues:
        by_env["test"][title_to_cat.get(issue.title, IssueCategory.PRODUCT)] += 1
    for issue in cmp.stage_issues:
        by_env["stage"][title_to_cat.get(issue.title, IssueCategory.PRODUCT)] += 1

    _writeln(out, f"  Уникальных title — TEST: {cmp.test_count}, STAGE: {cmp.stage_count}")
    _writeln(out, f"  Только TEST: {len(cmp.only_test)} | Только STAGE: {len(cmp.only_stage)} | В обоих: {len(cmp.in_both)}")
    for env, label in (("test", "TEST"), ("stage", "STAGE")):
        c = by_env[env]
        _writeln(
            out,
            f"  [{label}] продукт: {c[IssueCategory.PRODUCT]} | "
            f"инфра: {c[IssueCategory.INFRASTRUCTURE]} | шум: {c[IssueCategory.NOISE]}",
        )


def _print_risk_score(out, report: ProductQAReport) -> None:
    score = 0
    for a in report.all_analyzed:
        if a.analysis.category != IssueCategory.PRODUCT:
            continue
        if a.analysis.severity == Severity.BLOCKER:
            score += 10
        elif a.analysis.severity == Severity.HIGH:
            score += 5
        elif a.analysis.severity == Severity.MEDIUM:
            score += 2
        else:
            score += 1
    _writeln(out, f"  Release Risk Score (продукт): {score}  (blocker=10, high=5, medium=2, low=1)")
    _writeln(out, f"  Стоп-релиз (blocker product): {len(report.release_blockers)}")


def _print_cluster_summary(out, report: ProductQAReport) -> None:
    clusters: Counter = Counter()
    for a in report.all_analyzed:
        if a.analysis.category == IssueCategory.PRODUCT:
            clusters[a.analysis.cluster] += 1
    if not clusters:
        _writeln(out, "  (нет продуктовых)")
        return
    for cluster, count in clusters.most_common():
        _writeln(out, f"  • {cluster_label(cluster)}: {count}")


def _note_api_limit(out, cmp: EnvironmentComparison) -> None:
    if cmp.test_count + cmp.stage_count >= 100:
        _writeln(out, "  ⚠ API: до 100 issue на проект.")


def _print_analyzed_section(
    out,
    title: str,
    items: list[AnalyzedIssue],
    max_items: int,
    title_max: int,
    *,
    compact: bool = False,
) -> None:
    _section(out, title)
    if not items:
        _writeln(out, "  (нет)")
        _writeln(out, "")
        return

    sorted_items = sorted(
        items,
        key=lambda x: (
            _SEVERITY_ORDER.get(x.analysis.severity, 9),
            -x.analysis.user_impact,
            -x.issue.count,
        ),
    )
    shown = sorted_items[:max_items]
    for item in shown:
        if compact:
            _print_analyzed_compact(item, out, title_max=title_max)
        else:
            _print_analyzed_issue(item, out, title_max=title_max)

    remaining = len(sorted_items) - len(shown)
    if remaining > 0:
        _writeln(out, f"  … ещё {remaining}")
    _writeln(out, "")


def _print_env_only_section(
    out,
    title: str,
    issues: list[NormalizedIssue],
    report: ProductQAReport,
    max_items: int,
    title_max: int,
) -> None:
    title_to_analysis = {a.issue.title: a.analysis for a in report.all_analyzed}
    _section(out, title)
    if not issues:
        _writeln(out, "  (нет)")
        _writeln(out, "")
        return

    sorted_issues = sorted(issues, key=lambda i: (-i.count, i.title))
    for issue in sorted_issues[:max_items]:
        analysis = title_to_analysis.get(issue.title)
        cat = category_label(analysis.category) if analysis else "?"
        impact = f" impact={analysis.user_impact}/5" if analysis else ""
        title = compact_text(issue.title, max_len=title_max)
        _writeln(
            out,
            f"  • [{cat}{impact}] [{issue.level}] {title}  (count={issue.count}, id={issue.id})",
        )
    rest = len(sorted_issues) - min(len(sorted_issues), max_items)
    if rest > 0:
        _writeln(out, f"  … ещё {rest}")
    _writeln(out, "")


def _print_duplicate_groups(groups: list[TitleGroup], out, *, title_max: int) -> None:
    dup_groups = [g for g in groups if g.duplicate_ids > 0]
    if not dup_groups:
        _writeln(out, "  (дубликатов по title нет)")
        return
    for group in dup_groups[:12]:
        title = compact_text(group.title, max_len=title_max)
        _writeln(
            out,
            f"  • {title} — {len(group.issues)} id, {group.total_count} повторов",
        )


def _print_analyzed_issue(item: AnalyzedIssue, out, *, title_max: int) -> None:
    issue = item.issue
    analysis = item.analysis
    title = compact_text(issue.title, max_len=title_max)
    cat = category_label(analysis.category)

    _writeln(
        out,
        f"  ► [{analysis.severity.upper()}] [{cat}] impact={analysis.user_impact}/5 "
        f"repro={analysis.repro_likelihood.value}",
    )
    _writeln(out, f"      {title}")
    _writeln(out, f"      id={issue.id}  env={issue.environment}  count={issue.count}  level={issue.level}")
    _writeln(out, f"      last_seen={_format_dt(issue.last_seen)}")
    _writeln(out, f"      Кластер: {cluster_label(analysis.cluster)}")
    _writeln(out, f"      {compact_text(analysis.root_cause, max_len=title_max)}")
    if analysis.blocks_release:
        _writeln(out, "      ⛔ blocks_release=да")
    _writeln(out, "      QA:")
    for line in wrap_text(analysis.qa_explanation, width=66, indent="        "):
        _writeln(out, line)
    if issue.stack_trace:
        _writeln(out, f"      Stack: {compact_text(issue.stack_trace, max_len=title_max)}")
    _writeln(out, "")


def _print_analyzed_compact(item: AnalyzedIssue, out, *, title_max: int) -> None:
    issue = item.issue
    analysis = item.analysis
    title = compact_text(issue.title, max_len=title_max)
    _writeln(
        out,
        f"  • [{category_label(analysis.category)}] impact={analysis.user_impact}/5 "
        f"{title} (id={issue.id}, count={issue.count})",
    )


def _format_dt(dt: datetime) -> str:
    if dt.tzinfo:
        return dt.strftime("%Y-%m-%d %H:%M %Z")
    return dt.strftime("%Y-%m-%d %H:%M")


def _section(out, title: str) -> None:
    _writeln(out, title)
    _writeln(out, "-" * len(title))


def _line(out, char: str, width: int) -> None:
    _writeln(out, char * width)


def _center(out, text: str, width: int) -> None:
    _writeln(out, text.center(width))


def _writeln(out, text: str = "") -> None:
    out.write(text + "\n")


def is_critical(analysis: IssueAnalysis) -> bool:
    """Продуктовый риск для релиза (не инфра/шум)."""
    if analysis.category != IssueCategory.PRODUCT:
        return False
    return analysis.severity in (Severity.HIGH, Severity.BLOCKER) and analysis.user_impact >= 3
