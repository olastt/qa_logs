from __future__ import annotations

import os
import platform
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from qa_release_bot.analyzer import Severity
from qa_release_bot.models import NormalizedIssue
from qa_release_bot.report import (
    AnalyzedIssue,
    ProductQAReport,
    _DEFAULT_LIMITS,
    _SEVERITY_ORDER,
)
from qa_release_bot.taxonomy import category_label, cluster_label
from qa_release_bot.textfmt import compact_text

_FONT_NAME = "QAReportFont"
_FONT_REGISTERED = False


def write_pdf_report(
    reports: list[ProductQAReport],
    path: Path,
    *,
    limits: dict[str, int] | None = None,
) -> None:
    """Сохраняет QA-отчёт в PDF (UTF-8, кириллица через системный TTF)."""
    lim = {**_DEFAULT_LIMITS, **(limits or {})}
    title_max = lim["title_max_len"]
    path.parent.mkdir(parents=True, exist_ok=True)

    _ensure_font()
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="QA Release Report",
    )
    story: list = []

    story.append(Paragraph("QA RELEASE REPORT — Glitchtip", styles["title"]))
    story.append(
        Paragraph(
            f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["meta"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    if not reports:
        story.append(Paragraph("Нет данных. Проверьте .env и config/report.yaml.", styles["body"]))
        doc.build(story)
        return

    for report in reports:
        _build_product_pdf(story, report, styles, lim, title_max)

    doc.build(story)


def _build_product_pdf(
    story: list,
    report: ProductQAReport,
    styles: dict[str, ParagraphStyle],
    limits: dict[str, int],
    title_max: int,
) -> None:
    cmp = report.comparison
    story.append(Paragraph(f"Продукт: {escape(cmp.product_name)}", styles["h1"]))
    story.append(Paragraph(f"TEST → {escape(cmp.test_project)}", styles["body"]))
    story.append(Paragraph(f"STAGE → {escape(cmp.stage_project)}", styles["body"]))
    story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph("1. Сводка / Release Risk", styles["h2"]))
    for line in (
        f"TEST title: {cmp.test_count} | STAGE title: {cmp.stage_count}",
        f"Только TEST: {len(cmp.only_test)} | Только STAGE: {len(cmp.only_stage)}",
        f"Стоп-релиз (blocker product): {len(report.release_blockers)}",
    ):
        story.append(Paragraph(escape(line), styles["body"]))
    story.append(Spacer(1, 0.2 * cm))

    blockers = report.release_blockers or report.critical
    stage_new = report.product_new_in_stage or report.new_in_stage
    _pdf_analyzed_section(story, "2. BLOCKER (продукт)", blockers, styles, limits["max_critical"], title_max)
    _pdf_analyzed_section(story, "3. Продукт только STAGE", stage_new, styles, limits["max_new_in_stage"], title_max)
    _pdf_analyzed_section(story, "4. Регрессии (продукт)", report.regressions, styles, limits["max_regressions"], title_max)
    _pdf_analyzed_section(
        story,
        "5. Инфра (информационно)",
        report.infrastructure,
        styles,
        limits.get("max_infra", 15),
        title_max,
    )

    story.append(Paragraph("6. Дубликаты по title", styles["h2"]))
    story.append(Paragraph("TEST", styles["h3"]))
    _pdf_duplicates(story, report.test_groups, styles, title_max)
    story.append(Paragraph("STAGE", styles["h3"]))
    _pdf_duplicates(story, report.stage_groups, styles, title_max)

    _pdf_env_only(story, "7. Только в TEST", cmp.only_test, styles, limits["max_env_only_list"], title_max)
    _pdf_env_only(story, "8. Только в STAGE", cmp.only_stage, styles, limits["max_env_only_list"], title_max)
    story.append(Spacer(1, 0.5 * cm))


def _pdf_analyzed_section(
    story: list,
    title: str,
    items: list[AnalyzedIssue],
    styles: dict[str, ParagraphStyle],
    max_items: int,
    title_max: int,
) -> None:
    story.append(Paragraph(escape(title), styles["h2"]))
    if not items:
        story.append(Paragraph("(нет)", styles["muted"]))
        story.append(Spacer(1, 0.15 * cm))
        return

    sorted_items = sorted(
        items,
        key=lambda x: (
            _SEVERITY_ORDER.get(x.analysis.severity, 9),
            -x.analysis.user_impact,
            -x.issue.count,
        ),
    )
    for item in sorted_items[:max_items]:
        _pdf_analyzed_item(story, item, styles, title_max)
    rest = len(sorted_items) - min(len(sorted_items), max_items)
    if rest > 0:
        story.append(Paragraph(f"… ещё {rest}", styles["muted"]))
    story.append(Spacer(1, 0.15 * cm))


def _pdf_analyzed_item(
    story: list,
    item: AnalyzedIssue,
    styles: dict[str, ParagraphStyle],
    title_max: int,
) -> None:
    issue = item.issue
    analysis = item.analysis
    sev = analysis.severity.upper()
    color = colors.HexColor("#B71C1C") if analysis.severity == Severity.BLOCKER else colors.black
    title = compact_text(issue.title, max_len=title_max)

    cat = category_label(analysis.category)
    story.append(
        Paragraph(
            f"<b>[{sev}]</b> [{escape(cat)}] impact={analysis.user_impact}/5 "
            f"repro={analysis.repro_likelihood.value}",
            ParagraphStyle(
                "issue",
                parent=styles["body"],
                textColor=color,
                spaceBefore=4,
            ),
        )
    )
    story.append(Paragraph(escape(title), styles["body"]))
    meta = (
        f"id={issue.id} | {issue.environment} | count={issue.count} | "
        f"cluster={cluster_label(analysis.cluster)} | last_seen={_fmt_dt(issue.last_seen)}"
    )
    story.append(Paragraph(escape(meta), styles["small"]))
    story.append(Paragraph(f"Причина: {escape(compact_text(analysis.root_cause, max_len=title_max))}", styles["small"]))
    story.append(Paragraph(f"Регрессия: {'да' if analysis.regression else 'нет'}", styles["small"]))
    story.append(Paragraph(f"QA: {escape(analysis.qa_explanation)}", styles["small"]))
    if issue.stack_trace:
        story.append(
            Paragraph(
                f"Stack: {escape(compact_text(issue.stack_trace, max_len=title_max))}",
                styles["small"],
            )
        )


def _pdf_env_only(
    story: list,
    title: str,
    issues: list[NormalizedIssue],
    styles: dict[str, ParagraphStyle],
    max_items: int,
    title_max: int,
) -> None:
    story.append(Paragraph(escape(title), styles["h2"]))
    if not issues:
        story.append(Paragraph("(нет)", styles["muted"]))
        story.append(Spacer(1, 0.15 * cm))
        return

    sorted_issues = sorted(issues, key=lambda i: (-i.count, i.title))
    for issue in sorted_issues[:max_items]:
        t = compact_text(issue.title, max_len=title_max)
        story.append(
            Paragraph(
                escape(f"[{issue.level}] {t} (count={issue.count}, id={issue.id})"),
                styles["bullet"],
            )
        )
    rest = len(sorted_issues) - min(len(sorted_issues), max_items)
    if rest > 0:
        story.append(Paragraph(f"… ещё {rest}", styles["muted"]))
    story.append(Spacer(1, 0.15 * cm))


def _pdf_duplicates(
    story: list,
    groups: list,
    styles: dict[str, ParagraphStyle],
    title_max: int,
) -> None:
    dup = [g for g in groups if g.duplicate_ids > 0]
    if not dup:
        story.append(Paragraph("(дубликатов нет)", styles["muted"]))
        return
    for group in dup[:12]:
        title = compact_text(group.title, max_len=title_max)
        story.append(
            Paragraph(
                escape(
                    f"• {title} — {len(group.issues)} issue(s), "
                    f"суммарно {group.total_count} повторов"
                ),
                styles["bullet"],
            )
        )


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    font = _FONT_NAME
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Heading1"],
            fontName=font,
            fontSize=16,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.grey,
        ),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=font, fontSize=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font, fontSize=12, spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=font, fontSize=10, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName=font, fontSize=9, leading=12),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName=font,
            fontSize=8,
            leading=11,
            leftIndent=12,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontName=font,
            fontSize=8,
            leading=10,
            leftIndent=8,
            textColor=colors.HexColor("#333333"),
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base["Normal"],
            fontName=font,
            fontSize=8,
            textColor=colors.grey,
        ),
    }


def _ensure_font() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    path = _find_font_path()
    if not path:
        raise RuntimeError(
            "Не найден TTF-шрифт с кириллицей. Установите Arial (Windows) "
            "или DejaVu Sans (Linux), либо положите DejaVuSans.ttf в src/qa_release_bot/fonts/"
        )
    pdfmetrics.registerFont(TTFont(_FONT_NAME, str(path)))
    _FONT_REGISTERED = True


def _find_font_path() -> Path | None:
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


def _fmt_dt(dt: datetime) -> str:
    if dt.tzinfo:
        return dt.strftime("%Y-%m-%d %H:%M %Z")
    return dt.strftime("%Y-%m-%d %H:%M")
