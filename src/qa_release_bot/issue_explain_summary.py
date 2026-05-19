"""Развёрнутое «что случилось» для HTML/Markdown сводки."""

from __future__ import annotations

from qa_release_bot.issue_explain import _UNCLEAR_PREFIX
from qa_release_bot.issue_record import IssueRecord, StackFrame
from qa_release_bot.module_map import ModuleResolution


def build_summary_what_happened(
    issue: IssueRecord,
    resolution: ModuleResolution,
    base_what: str,
    *,
    hypothesis: str | None,
) -> str:
    parts: list[str] = []

    if resolution.human_module:
        parts.append(f"Раздел: {resolution.human_module}.")
    elif resolution.controller_key:
        parts.append(f"Компонент: {resolution.controller_key}.")

    what = base_what.strip()
    if what.startswith(_UNCLEAR_PREFIX):
        what = what[len(_UNCLEAR_PREFIX) :].strip()
    if what:
        parts.append(what)

    frame = _best_stack_frame(issue)
    if frame:
        parts.append(f"В коде: {frame.display()}.")

    culprit = (issue.culprit or "").strip()
    if culprit and culprit.lower() not in what.lower():
        parts.append(f"Контекст выполнения: {culprit[:220]}.")

    meta = issue.metadata or {}
    meta_bits: list[str] = []
    exc_type = meta.get("type")
    exc_val = meta.get("value")
    if exc_type:
        meta_bits.append(str(exc_type))
    if exc_val and str(exc_val) not in what:
        meta_bits.append(str(exc_val)[:180])
    filename = meta.get("filename")
    function = meta.get("function")
    if filename or function:
        loc = f"{function or '?'} ({filename or '?'})"
        if loc not in what and (not frame or loc not in frame.display()):
            meta_bits.append(loc)
    if meta_bits:
        parts.append("Из лога: " + " — ".join(meta_bits) + ".")

    if hypothesis:
        parts.append(f"Вероятная причина: {hypothesis}")

    text = " ".join(p.strip() for p in parts if p.strip())
    return text or base_what or issue.title[:300]


def _best_stack_frame(issue: IssueRecord) -> StackFrame | None:
    frames = issue.stack_frames or []
    if not frames:
        return None
    for frame in reversed(frames):
        if frame.in_app and (frame.function or frame.filename):
            return frame
    return frames[-1]
