from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from qa_release_bot.models import NormalizedIssue
from qa_release_bot.taxonomy import (
    IssueCategory,
    IssueTaxonomy,
    ReproLikelihood,
    RootCauseCluster,
    category_label,
    classify_taxonomy,
    cluster_label,
)


class Severity(StrEnum):
    """Release risk — не уровень Sentry."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKER = "blocker"


@dataclass(slots=True)
class IssueAnalysis:
    taxonomy: IssueTaxonomy
    severity: Severity
    regression: bool
    root_cause: str
    qa_explanation: str
    blocks_release: bool

    @property
    def category(self) -> IssueCategory:
        return self.taxonomy.category

    @property
    def cluster(self) -> RootCauseCluster:
        return self.taxonomy.cluster

    @property
    def user_impact(self) -> int:
        return self.taxonomy.user_impact

    @property
    def repro_likelihood(self) -> ReproLikelihood:
        return self.taxonomy.repro_likelihood


def analyze_issue(issue: NormalizedIssue, *, only_in_stage: bool = False) -> IssueAnalysis:
    """Классификация для release risk (эвристики; позже — LLM)."""
    taxonomy = classify_taxonomy(issue, only_in_stage=only_in_stage)
    severity = _release_severity(issue, taxonomy, only_in_stage=only_in_stage)
    regression = _is_regression(issue, taxonomy, only_in_stage=only_in_stage, severity=severity)
    root_cause = _describe_root_cause(issue, taxonomy)
    explanation = _qa_explanation(issue, taxonomy, severity, regression)
    blocks = _blocks_release(taxonomy, severity, only_in_stage=only_in_stage)

    return IssueAnalysis(
        taxonomy=taxonomy,
        severity=severity,
        regression=regression,
        root_cause=root_cause,
        qa_explanation=explanation,
        blocks_release=blocks,
    )


def _release_severity(
    issue: NormalizedIssue,
    taxonomy: IssueTaxonomy,
    *,
    only_in_stage: bool,
) -> Severity:
    if taxonomy.category in (IssueCategory.INFRASTRUCTURE, IssueCategory.NOISE):
        if taxonomy.user_impact >= 2 and taxonomy.category == IssueCategory.INFRASTRUCTURE:
            return Severity.LOW
        return Severity.LOW

    impact = taxonomy.user_impact
    if impact >= 5:
        return Severity.BLOCKER
    if impact >= 4:
        return Severity.BLOCKER if only_in_stage or issue.environment == "stage" else Severity.HIGH
    if impact >= 3:
        return Severity.HIGH if only_in_stage else Severity.MEDIUM
    if impact >= 2:
        return Severity.MEDIUM
    return Severity.LOW


def _is_regression(
    issue: NormalizedIssue,
    taxonomy: IssueTaxonomy,
    *,
    only_in_stage: bool,
    severity: Severity,
) -> bool:
    if not only_in_stage:
        return False
    if taxonomy.category != IssueCategory.PRODUCT:
        return False
    return severity in (Severity.BLOCKER, Severity.HIGH) or taxonomy.user_impact >= 3


def _blocks_release(taxonomy: IssueTaxonomy, severity: Severity, *, only_in_stage: bool) -> bool:
    if taxonomy.category != IssueCategory.PRODUCT:
        return False
    if severity != Severity.BLOCKER:
        return False
    return taxonomy.user_impact >= 4 and (only_in_stage or severity == Severity.BLOCKER)


def _describe_root_cause(issue: NormalizedIssue, taxonomy: IssueTaxonomy) -> str:
    meta = issue.metadata
    location = meta.get("function") or meta.get("filename") or "неизвестное место"
    exc_type = meta.get("type") or "Error"
    base = f"[{cluster_label(taxonomy.cluster)}] {exc_type} в {location}"
    if taxonomy.cluster_detail:
        base += f" — {taxonomy.cluster_detail}"
    return base


def _qa_explanation(
    issue: NormalizedIssue,
    taxonomy: IssueTaxonomy,
    severity: Severity,
    regression: bool,
) -> str:
    cat = category_label(taxonomy.category)
    parts = [
        f"Категория: {cat}. Кластер: {cluster_label(taxonomy.cluster)}.",
        f"User impact: {taxonomy.user_impact}/5. "
        f"Repro: {taxonomy.repro_likelihood.value}.",
        f"Окружение: {issue.environment}, повторов: {issue.count}.",
    ]

    if taxonomy.category == IssueCategory.INFRASTRUCTURE:
        parts.append("Инфра/интеграция — не стоп релиза UI, unless core flow зависит от сервиса.")
    elif taxonomy.category == IssueCategory.NOISE:
        parts.append("Шум/валидация — проверить данные и приоритет ниже продуктовых багов.")
    elif severity == Severity.BLOCKER:
        parts.append("Ломает продуктовый флоу или целостность данных — стоп релиза или явный risk accept.")
    elif severity == Severity.HIGH:
        parts.append("Бизнес-логика / UX — проверить сценарий на stage перед релизом.")
    else:
        parts.append("Можно в бэклог, если не в зоне текущих изменений.")

    if regression:
        parts.append("Регрессия stage: на test этого title нет — приоритет для QA на stage.")

    return " ".join(parts)
