from __future__ import annotations

import re


def compact_text(text: str, *, max_len: int = 80) -> str:
    """Одна строка без лишних пробелов, обрезка длинных title (SQL и т.д.)."""
    one_line = re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", " ")).strip()
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1].rstrip() + "…"


def wrap_text(text: str, *, width: int = 68, indent: str = "      ") -> list[str]:
    words = text.split()
    if not words:
        return [indent + "(пусто)"]
    lines: list[str] = []
    current = indent
    for word in words:
        candidate = current + (" " if current != indent else "") + word
        if len(candidate) > width and current != indent:
            lines.append(current)
            current = indent + word
        else:
            current = candidate
    if current.strip():
        lines.append(current)
    return lines
