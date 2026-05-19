from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from qa_release_bot.analyst_pdf import (
    BANNER,
    C_DIVIDER,
    C_HEADER_BG,
    C_HEADER_TEXT,
    C_TEXT,
    C_TEXT_SEC,
    PdfBuildResult,
    _MONTHS_RU,
    _build_styles,
    blockers_high_flow,
    format_summary_message,
    medium_low_table_flow,
    new_issues_flow,
)
from qa_release_bot.pdf_fonts import ensure_pdf_font, ensure_pdf_font_bold
from qa_release_bot.summary_report import SummaryReport


def default_summary_pdf_path(output_dir: Path, report: SummaryReport) -> Path:
    day = report.fetched_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    slug = report.project_slug.replace("/", "-")
    return output_dir / f"summary_{slug}_{day}.pdf"


def write_summary_pdf(report: SummaryReport, path: Path) -> PdfBuildResult:
    font = ensure_pdf_font()
    font_bold = ensure_pdf_font_bold()
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles(font, font_bold)
    meta = _pdf_meta(report)
    page_num = {"n": 0}

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
    )
    w = doc.width
    story: list = []

    def _on_page(canvas, _doc):
        page_num["n"] = canvas.getPageNumber()
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(C_TEXT_SEC)
        footer = (
            f"Стр. {canvas.getPageNumber()} • {meta['product']} • "
            f"{report.instance} • {meta['date_short']}"
        )
        canvas.drawCentredString(A4[0] / 2, 12 * mm, footer)
        canvas.restoreState()

    story.extend(_cover(report, styles, w, meta))
    story.append(PageBreak())

    new_block = new_issues_flow(
        report.new_issues,
        is_first_run=report.is_first_run,
        styles=styles,
        width=w,
    )
    if new_block:
        story.extend(new_block)
        story.append(PageBreak())

    bh = blockers_high_flow(
        report.blockers,
        report.highs,
        styles,
        w,
        empty_message="Нет blocker/high.",
    )
    if bh:
        story.extend(bh)
        story.append(PageBreak())

    ml = medium_low_table_flow(
        report.mediums,
        report.lows,
        env_label="test",
        styles=styles,
        width=w,
    )
    if ml:
        story.extend(ml)

    noise = _noise_section(report, styles, w)
    if noise:
        story.append(Spacer(1, 4 * mm))
        story.extend(noise)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    return PdfBuildResult(
        path=path,
        page_count=page_num["n"],
        blockers=len(report.blockers),
        highs=len(report.highs),
        mediums=len(report.mediums),
        lows=len(report.lows),
    )


def _pdf_meta(report: SummaryReport) -> dict:
    now = report.fetched_at.astimezone(timezone.utc)
    return {
        "product": report.product_name,
        "date_short": f"{now.day} {_MONTHS_RU[now.month - 1]} {now.year}",
    }


def _cover(report: SummaryReport, styles: dict, width: float, meta: dict) -> list:
    now = report.fetched_at.astimezone(timezone.utc)
    header = Table(
        [
            [Paragraph("📋  Сводка логов", styles["cover_title"])],
            [Paragraph(escape(report.product_name), styles["cover_title"])],
            [Paragraph(
                f"{meta['date_short']} · {escape(report.instance)} / {escape(report.project_slug)}",
                styles["cover_title"],
            )],
        ],
        colWidths=[width],
    )
    header.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_HEADER_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 16),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ])
    )

    vcolor, vtext = BANNER.get(report.decision.verdict, BANNER["ok"])
    banner = Table([[Paragraph(vtext, styles["verdict"])]], colWidths=[width])
    banner.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), vcolor),
            ("TOPPADDING", (0, 0), (-1, -1), 20),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ])
    )

    tw = width / 4
    tiles = Table(
        [
            [
                Paragraph(str(len(report.blockers)), styles["tile_num"]),
                Paragraph(str(len(report.highs)), styles["tile_num"]),
                Paragraph(str(len(report.mediums)), styles["tile_num"]),
                Paragraph(str(len(report.lows)), styles["tile_num"]),
            ],
            [
                Paragraph("BLOCKER", styles["tile_lbl"]),
                Paragraph("HIGH", styles["tile_lbl"]),
                Paragraph("MEDIUM", styles["tile_lbl"]),
                Paragraph("LOW", styles["tile_lbl"]),
            ],
        ],
        colWidths=[tw] * 4,
    )
    tiles.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, C_DIVIDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, C_DIVIDER),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ])
    )

    product = len(report.blockers) + len(report.highs) + len(report.mediums) + len(report.lows)
    footer_parts: list = [
        Paragraph(
            f"API: {report.total_unresolved} нерешённых · "
            f"после шума: {product} · "
            f"{escape(report.issue_query)} · {report.stats_period} · "
            f"{now.strftime('%H:%M UTC')}",
            styles["body"],
        ),
    ]
    if report.decision.headline:
        footer_parts.append(Spacer(1, 2 * mm))
        footer_parts.append(Paragraph(escape(report.decision.headline), styles["small"]))
    for item in report.decision.items[:3]:
        footer_parts.append(Paragraph(escape(item), styles["small"]))

    return [header, Spacer(1, 5 * mm), banner, Spacer(1, 5 * mm), tiles, Spacer(1, 4 * mm), *footer_parts]


def _noise_section(report: SummaryReport, styles: dict, width: float) -> list:
    if not report.noise_groups:
        return []
    flow = [
        Paragraph("🗑️ ШУМ (сгруппировано)", styles["section"]),
        HRFlowable(width="100%", thickness=1, color=C_DIVIDER),
    ]
    for g in report.noise_groups:
        flow.append(
            Paragraph(
                f"• {escape(g.label)} — {g.total_count} повторов ({g.issue_count} issue)",
                styles["body"],
            )
        )
    return flow
