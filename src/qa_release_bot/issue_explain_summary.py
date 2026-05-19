"""Развёрнутое «что случилось» для HTML/Markdown сводки."""

from __future__ import annotations

from qa_release_bot.issue_explain import _UNCLEAR_PREFIX
from qa_release_bot.issue_plain_explain import TesterExplanation
from qa_release_bot.issue_record import IssueRecord, StackFrame
from qa_release_bot.module_map import ModuleResolution


def build_summary_what_happened(
    issue: IssueRecord,
    resolution: ModuleResolution,
    base_what: str,
    *,
    hypothesis: str | None,
    plain: TesterExplanation | None = None,
) -> str:
    """Краткое «подробнее» — без дублирования plain_one_liner."""
    if plain and plain.details:
        return plain.details

    parts: list[str] = []
    frame = _best_stack_frame(issue)
    if frame:
        parts.append(f"Место в коде: {frame.display()}.")
    culprit = (issue.culprit or "").strip()
    if culprit:
        parts.append(f"Запрос/действие: {culprit[:200]}.")

    what = base_what.strip()
    if what.startswith(_UNCLEAR_PREFIX):
        what = what[len(_UNCLEAR_PREFIX) :].strip()
    if what and what.lower() not in " ".join(parts).lower():
        parts.append(what)

    text = " ".join(p.strip() for p in parts if p.strip())
    return text or issue.title[:200]


def _best_stack_frame(issue: IssueRecord) -> StackFrame | None:
    frames = issue.stack_frames or []
    if not frames:
        return None
    for frame in reversed(frames):
        if frame.in_app and (frame.function or frame.filename):
            return frame
    return frames[-1]
