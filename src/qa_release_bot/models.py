from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ReleaseVerdict(StrEnum):
    """Решение QA по issue для релиза."""

    BLOCKER = "blocker"  # блокер релиза
    DEFER = "defer"  # можно отложить
    REGRESSION = "regression"  # регрессия


@dataclass(frozen=True, slots=True)
class GlitchtipProjectRef:
    instance: str
    org_slug: str
    slug: str
    label: str | None = None

    @property
    def display_name(self) -> str:
        return self.label or self.slug


@dataclass(slots=True)
class GlitchtipIssue:
    """Нормализованный issue из Sentry-совместимого API."""

    id: str
    short_id: str
    project: GlitchtipProjectRef
    title: str
    culprit: str
    level: str
    status: str
    count: int
    user_count: int
    first_seen: datetime
    last_seen: datetime
    project_numeric_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Ключ для группировки похожих ошибок (заглушка — уточним в grouper)."""
        exc_type = self.metadata.get("type") or ""
        exc_value = self.metadata.get("value") or ""
        filename = self.metadata.get("filename") or ""
        function = self.metadata.get("function") or ""
        return "|".join(
            [
                self.project.instance,
                self.project.slug,
                exc_type,
                exc_value,
                filename,
                function,
            ]
        )


@dataclass(slots=True)
class IssueGroup:
    """Сгруппированные похожие issues."""

    fingerprint: str
    issues: list[GlitchtipIssue]
    verdict: ReleaseVerdict | None = None
    verdict_reason: str = ""


@dataclass(slots=True)
class NewIssueAlert:
    """Новый issue, которого не было в локальном state."""

    issue: GlitchtipIssue
    verdict: ReleaseVerdict
    verdict_reason: str


@dataclass(slots=True)
class NormalizedIssue:
    """Единая структура ошибки для QA-отчёта."""

    id: str
    short_id: str
    title: str
    level: str
    count: int
    last_seen: datetime
    stack_trace: str | None
    environment: str
    project_slug: str
    instance: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TitleGroup:
    """Несколько issue с одинаковым title (дубликаты)."""

    title: str
    issues: list[NormalizedIssue]

    @property
    def total_count(self) -> int:
        return sum(i.count for i in self.issues)

    @property
    def duplicate_ids(self) -> int:
        return max(0, len(self.issues) - 1)

    @property
    def representative(self) -> NormalizedIssue:
        return max(self.issues, key=lambda i: (i.count, i.last_seen))
