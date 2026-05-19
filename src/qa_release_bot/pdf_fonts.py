from __future__ import annotations

import os
import platform
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME = "QAReportFont"
FONT_NAME_BOLD = "QAReportFont-Bold"
_FONT_REGISTERED = False
_BOLD_REGISTERED = False


def ensure_pdf_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return FONT_NAME
    path = find_font_path()
    if not path:
        raise RuntimeError(
            "Не найден TTF-шрифт с кириллицей (Arial / DejaVuSans в src/qa_release_bot/fonts/)."
        )
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(path)))
    _FONT_REGISTERED = True
    return FONT_NAME


def ensure_pdf_font_bold() -> str:
    """Жирный шрифт для заголовков таблиц; при отсутствии — обычный."""
    global _BOLD_REGISTERED
    ensure_pdf_font()
    if _BOLD_REGISTERED:
        return FONT_NAME_BOLD
    bold_path = find_bold_font_path()
    if bold_path:
        pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, str(bold_path)))
        _BOLD_REGISTERED = True
        return FONT_NAME_BOLD
    return FONT_NAME


def find_font_path() -> Path | None:
    bundled = Path(__file__).parent / "fonts" / "DejaVuSans.ttf"
    candidates = [
        bundled,
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    if platform.system() == "Windows":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates.extend([windir / "arial.ttf", windir / "Arial.ttf"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_bold_font_path() -> Path | None:
    bundled = Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"
    regular = find_font_path()
    candidates = [
        bundled,
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\Arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    if regular and regular.name.lower().startswith("arial"):
        candidates.insert(0, regular.parent / "arialbd.ttf")
    if platform.system() == "Windows":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates.extend([windir / "arialbd.ttf", windir / "Arialbd.ttf"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
