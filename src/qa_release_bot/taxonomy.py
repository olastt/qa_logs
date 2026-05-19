from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from qa_release_bot.models import NormalizedIssue


class IssueCategory(StrEnum):
    """Тип сигнала в Glitchtip — не всё равно риск релиза."""

    PRODUCT = "product"  # баг приложения / бизнес-логики
    INFRASTRUCTURE = "infrastructure"  # окружение, интеграции, внешние сервисы
    NOISE = "noise"  # warnings, слабая валидация, тестовый мусор


class RootCauseCluster(StrEnum):
    NULL_HANDLING = "null_handling"
    DB_INTEGRITY = "db_integrity"
    EXTERNAL_SERVICES = "external_services"
    TYPE_MISMATCH = "type_mismatch"
    CONFIG_ENV = "config_env"
    VALIDATION_WARNING = "validation_warning"
    UNKNOWN = "unknown"


class ReproLikelihood(StrEnum):
    DETERMINISTIC = "deterministic"
    INTERMITTENT = "intermittent"
    ENV_SPECIFIC = "env_specific"


# Подстроки в title/stack (нижний регистр)
_INFRA_PATTERNS = (
    "rabbitmq",
    "clickhouse",
    "cdn",
    "nohup",
    "потребление памяти",
    "memory",
    "stream_socket_client",
    "connection timed out",
    "can't connect",
    "cant connect",
    "circuit_breaker",
    "marking_code",
    "prescription.error",
    "client error: `post",
    "failed to fetch",
    "logs has not been saved",
)

_NOISE_PATTERNS = (
    "file_put_contents",
    "undefined array key",
    "trying to access array offset",
    "permission denied",
    "build/tasks/",
)

_CORE_FLOW_PATTERNS = (
    "medicalcard",
    "diagnoses",
    "invoice",
    "admission",
    "приём",
    "прием",
    "client",
    "patient",
    "pet",
    "goodentity",
    "erestcontroller",
    "invoicedocument",
    "medicalcards",
)

_NULL_PATTERNS = (
    "cannot assign null",
    "on null",
    "hasattribute() on null",
    "must not be accessed on null",
)

_DB_INTEGRITY_PATTERNS = (
    "integrity constraint",
    "foreign key",
    "cannot delete or update a parent row",
    "1451 ",
    "23000",
    "column not found",
    "42s22",
    "active record",
    "cdbcommand",
    "cdbexception",
)

_TYPE_MISMATCH_PATTERNS = (
    "typeerror",
    "count(): argument",
    "must be of type",
    "countable|array",
)


@dataclass(frozen=True, slots=True)
class IssueTaxonomy:
    category: IssueCategory
    cluster: RootCauseCluster
    user_impact: int  # 0–5: влияние на пользовательский флоу
    repro_likelihood: ReproLikelihood
    cluster_detail: str = ""


def classify_taxonomy(issue: NormalizedIssue, *, only_in_stage: bool) -> IssueTaxonomy:
    text = _issue_blob(issue)

    category = _detect_category(text, issue)
    cluster = _detect_cluster(text, issue, category)
    user_impact = _score_user_impact(text, issue, category, cluster)
    repro = _score_repro(issue, only_in_stage=only_in_stage, category=category, cluster=cluster)

    detail = _cluster_detail(cluster, text)
    return IssueTaxonomy(
        category=category,
        cluster=cluster,
        user_impact=user_impact,
        repro_likelihood=repro,
        cluster_detail=detail,
    )


def _issue_blob(issue: NormalizedIssue) -> str:
    parts = [issue.title, issue.stack_trace or ""]
    meta = issue.metadata
    parts.extend(str(meta.get(k, "")) for k in ("type", "value", "function", "filename"))
    return " ".join(parts).lower()


def _detect_category(text: str, issue: NormalizedIssue) -> IssueCategory:
    if any(p in text for p in _NOISE_PATTERNS):
        if issue.level == "warning" or "undefined array key" in text or "file_put_contents" in text:
            return IssueCategory.NOISE
    if any(p in text for p in _INFRA_PATTERNS):
        return IssueCategory.INFRASTRUCTURE
    if issue.level == "warning" and not any(p in text for p in _DB_INTEGRITY_PATTERNS):
        return IssueCategory.NOISE
    if any(p in text for p in _NULL_PATTERNS + _DB_INTEGRITY_PATTERNS + _TYPE_MISMATCH_PATTERNS):
        return IssueCategory.PRODUCT
    if any(p in text for p in _CORE_FLOW_PATTERNS):
        return IssueCategory.PRODUCT
    if issue.level in ("fatal", "error") and "exception" in text:
        return IssueCategory.PRODUCT
    if any(p in text for p in _INFRA_PATTERNS):
        return IssueCategory.INFRASTRUCTURE
    return IssueCategory.NOISE if issue.level == "warning" else IssueCategory.PRODUCT


def _detect_cluster(text: str, issue: NormalizedIssue, category: IssueCategory) -> RootCauseCluster:
    if category == IssueCategory.INFRASTRUCTURE:
        return RootCauseCluster.EXTERNAL_SERVICES
    if category == IssueCategory.NOISE:
        return RootCauseCluster.VALIDATION_WARNING
    if any(p in text for p in _NULL_PATTERNS):
        return RootCauseCluster.NULL_HANDLING
    if any(p in text for p in _DB_INTEGRITY_PATTERNS):
        return RootCauseCluster.DB_INTEGRITY
    if any(p in text for p in _TYPE_MISMATCH_PATTERNS):
        return RootCauseCluster.TYPE_MISMATCH
    if "rabbitmq" in text or "clickhouse" in text or "client error" in text:
        return RootCauseCluster.EXTERNAL_SERVICES
    if only_env_hint(text, issue):
        return RootCauseCluster.CONFIG_ENV
    return RootCauseCluster.UNKNOWN


def only_env_hint(text: str, issue: NormalizedIssue) -> bool:
    return "prescriptions-test" in text or "kube-dev" in text and "stage" in issue.environment


def _score_user_impact(
    text: str,
    issue: NormalizedIssue,
    category: IssueCategory,
    cluster: RootCauseCluster,
) -> int:
    if category == IssueCategory.INFRASTRUCTURE:
        if "rabbitmq" in text and any(c in text for c in ("invoice", "payment", "queue-workers")):
            return 2
        return 1
    if category == IssueCategory.NOISE:
        return 1 if issue.count >= 20 else 0

    score = 2
    if any(p in text for p in _CORE_FLOW_PATTERNS):
        score += 2
    if cluster == RootCauseCluster.NULL_HANDLING:
        score += 2
    if cluster == RootCauseCluster.DB_INTEGRITY:
        score += 2
    if cluster == RootCauseCluster.TYPE_MISMATCH:
        score += 1
    if issue.level == "fatal":
        score += 1
    if "medicalcard" in text and "null" in text:
        score = 5
    return min(5, max(0, score))


def _score_repro(
    issue: NormalizedIssue,
    *,
    only_in_stage: bool,
    category: IssueCategory,
    cluster: RootCauseCluster,
) -> ReproLikelihood:
    if only_in_stage and category == IssueCategory.PRODUCT:
        return ReproLikelihood.ENV_SPECIFIC
    if category == IssueCategory.INFRASTRUCTURE:
        return ReproLikelihood.INTERMITTENT
    if cluster in (RootCauseCluster.NULL_HANDLING, RootCauseCluster.DB_INTEGRITY):
        return ReproLikelihood.DETERMINISTIC if issue.count >= 3 else ReproLikelihood.INTERMITTENT
    if issue.count >= 50:
        return ReproLikelihood.DETERMINISTIC
    return ReproLikelihood.INTERMITTENT


def _cluster_detail(cluster: RootCauseCluster, text: str) -> str:
    if cluster == RootCauseCluster.NULL_HANDLING and "medicalcard" in text:
        return "DATA INTEGRITY: null в сущности (MedicalCard / связанные поля)"
    if cluster == RootCauseCluster.DB_INTEGRITY:
        m = re.search(r"sqlstate\[(\w+)\]", text)
        if m:
            return f"SQLSTATE {m.group(1).upper()}"
    return ""


_CLUSTER_LABEL = {
    RootCauseCluster.NULL_HANDLING: "Null handling",
    RootCauseCluster.DB_INTEGRITY: "DB integrity",
    RootCauseCluster.EXTERNAL_SERVICES: "External services",
    RootCauseCluster.TYPE_MISMATCH: "Type mismatch",
    RootCauseCluster.CONFIG_ENV: "Config / env",
    RootCauseCluster.VALIDATION_WARNING: "Validation / warnings",
    RootCauseCluster.UNKNOWN: "Unknown",
}

_CATEGORY_LABEL = {
    IssueCategory.PRODUCT: "Продукт",
    IssueCategory.INFRASTRUCTURE: "Инфра / интеграции",
    IssueCategory.NOISE: "Шум",
}


def cluster_label(cluster: RootCauseCluster) -> str:
    return _CLUSTER_LABEL.get(cluster, cluster.value)


def category_label(category: IssueCategory) -> str:
    return _CATEGORY_LABEL.get(category, category.value)
