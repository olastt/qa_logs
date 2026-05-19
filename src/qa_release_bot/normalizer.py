from __future__ import annotations

from datetime import datetime
from typing import Any

from qa_release_bot.models import GlitchtipIssue, NormalizedIssue


def normalize_issue(issue: GlitchtipIssue, *, environment: str) -> NormalizedIssue:
    """Приводит issue Glitchtip к единой структуре для отчёта."""
    return NormalizedIssue(
        id=issue.id,
        short_id=issue.short_id,
        title=_normalize_title(issue.title),
        level=issue.level.lower(),
        count=issue.count,
        last_seen=issue.last_seen,
        stack_trace=build_stack_trace_summary(issue.metadata, issue.culprit),
        environment=environment,
        project_slug=issue.project.slug,
        instance=issue.project.instance,
        metadata=issue.metadata,
    )


def normalize_issues(issues: list[GlitchtipIssue], *, environment: str) -> list[NormalizedIssue]:
    return [normalize_issue(i, environment=environment) for i in issues]


def build_stack_trace_summary(metadata: dict[str, Any], culprit: str = "") -> str | None:
    """
    Краткий stack trace из metadata issue.

    Glitchtip/Sentry часто отдают type, value, filename, function без полного стека.
    """
    exc_type = metadata.get("type")
    exc_value = metadata.get("value")
    filename = metadata.get("filename")
    function = metadata.get("function")

    if not any((exc_type, exc_value, filename, function, culprit)):
        return None

    lines: list[str] = []
    if exc_type or exc_value:
        type_part = exc_type or "Exception"
        value_part = f": {exc_value}" if exc_value else ""
        lines.append(f"{type_part}{value_part}")

    if function or filename:
        location = function or "?"
        file_part = f" ({filename})" if filename else ""
        lines.append(f"  at {location}{file_part}")

    if culprit and culprit not in "".join(lines):
        lines.append(f"  culprit: {culprit}")

    return "\n".join(lines)


def _normalize_title(title: str) -> str:
    return " ".join(title.split())
