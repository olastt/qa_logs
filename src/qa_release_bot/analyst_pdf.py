from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from qa_release_bot.issue_analysis import analyze_issue_full, format_analysis_plain
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.markdown_report import AnalystReport
from qa_release_bot.pdf_fonts import ensure_pdf_font, ensure_pdf_font_bold
from qa_release_bot.severity_rules import IssueSeverity, classify_severity
from qa_release_bot.textfmt import compact_text
from qa_release_bot.tuesday_diff import is_stale

C_HEADER_BG = colors.HexColor("#1A1A2E")
C_HEADER_TEXT = colors.HexColor("#FFFFFF")
C_TEXT = colors.HexColor("#2D3748")
C_TEXT_SEC = colors.HexColor("#718096")
C_DIVIDER = colors.HexColor("#E2E8F0")
C_STALE_BG = colors.HexColor("#F7FAFC")
C_BADGE_COUNT = colors.HexColor("#EBF8FF")
C_BADGE_DATE = colors.HexColor("#FAF5FF")
C_ENV_STAGE = colors.HexColor("#3182CE")
C_ENV_TEST = colors.HexColor("#805AD5")

SEV_STYLE = {
    IssueSeverity.BLOCKER: (colors.HexColor("#E53E3E"), colors.HexColor("#FFF5F5"), "BLOCKER"),
    IssueSeverity.HIGH: (colors.HexColor("#DD6B20"), colors.HexColor("#FFFAF0"), "HIGH"),
    IssueSeverity.MEDIUM: (colors.HexColor("#D69E2E"), colors.HexColor("#FFFFF0"), "MEDIUM"),
    IssueSeverity.LOW: (colors.HexColor("#38A169"), colors.HexColor("#F0FFF4"), "LOW"),
}

BANNER = {
    "forbidden": (colors.HexColor("#E53E3E"), "РЕЛИЗ ЗАПРЕЩЁН"),
    "risk": (colors.HexColor("#DD6B20"), "РЕЛИЗ С РИСКОМ"),
    "ok": (colors.HexColor("#38A169"), "РЕЛИЗ ОК"),
}

_BAR_WIDTH = 80
_BAR_HEIGHT = 10
_BAR_BG = colors.HexColor("#E2E8F0")
_BAR_COLORS = {
    "MEDIUM": colors.HexColor("#D69E2E"),
    "LOW": colors.HexColor("#38A169"),
}
_ML_COL_RATIOS = (55, 220, 85, 40, 50, 40)

_MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


@dataclass(slots=True)
class PdfBuildResult:
    path: Path
    page_count: int
    blockers: int
    highs: int
    mediums: int
    lows: int


def write_analyst_pdf(report: AnalystReport, path: Path) -> PdfBuildResult:
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
        footer = f"Стр. {canvas.getPageNumber()} • {meta['product']} • {meta['date_short']}"
        canvas.drawCentredString(A4[0] / 2, 12 * mm, footer)
        canvas.restoreState()

    story.extend(_cover(report, styles, w, meta))
    story.append(PageBreak())

    new_block = _new_issues_page(report, styles, w)
    if new_block:
        story.extend(new_block)
        story.append(PageBreak())

    bh = _blockers_high(report, styles, w)
    if bh:
        story.extend(bh)
        story.append(PageBreak())

    dr = _diff_regressions(report, styles, w)
    if dr:
        story.extend(dr)
        story.append(PageBreak())

    ml = _medium_low_table(report, styles, w)
    if ml:
        story.extend(ml)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    return PdfBuildResult(
        path=path,
        page_count=page_num["n"],
        blockers=len(report.blockers),
        highs=len(report.highs),
        mediums=len(report.mediums),
        lows=len(report.lows),
    )


def default_pdf_path(output_dir: Path, fetched_at: datetime) -> Path:
    day = fetched_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return output_dir / f"qa_report_{day}.pdf"


def format_summary_message(result: PdfBuildResult) -> str:
    return (
        f"✅ PDF сохранён: {result.path.resolve()}\n"
        f"📄 Страниц: {result.page_count}\n"
        f"🔴 Блокеров: {result.blockers}  "
        f"🟠 High: {result.highs}  "
        f"🟡 Medium: {result.mediums}  "
        f"🟢 Low: {result.lows}"
    )


def _pdf_meta(report: AnalystReport) -> dict:
    now = report.fetched_at.astimezone(timezone.utc)
    return {
        "product": report.product_name,
        "date_short": f"{now.day} {_MONTHS_RU[now.month - 1]} {now.year}",
        "date_full": now.strftime("%Y-%m-%d"),
    }


def _build_styles(font: str, font_bold: str | None = None) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    bold = font_bold or font
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Normal"], fontName=font, fontSize=20,
            textColor=C_HEADER_TEXT, leading=24,
        ),
        "verdict": ParagraphStyle(
            "verdict", parent=base["Normal"], fontName=font, fontSize=36,
            textColor=C_HEADER_TEXT, alignment=TA_CENTER, leading=40,
        ),
        "tile_num": ParagraphStyle(
            "tile_num", parent=base["Normal"], fontName=font, fontSize=48,
            textColor=C_TEXT, alignment=TA_CENTER, leading=52,
        ),
        "tile_lbl": ParagraphStyle(
            "tile_lbl", parent=base["Normal"], fontName=font, fontSize=10,
            textColor=C_TEXT_SEC, alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Normal"], fontName=font, fontSize=14,
            textColor=C_TEXT, spaceBefore=4, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontName=font, fontSize=11,
            leading=14, textColor=C_TEXT,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontName=font, fontSize=10,
            leading=12, textColor=C_TEXT_SEC,
        ),
        "card_title": ParagraphStyle(
            "card_title", parent=base["Normal"], fontName=font, fontSize=11,
            leading=14, textColor=C_TEXT,
        ),
        "stale_badge": ParagraphStyle(
            "stale_badge", parent=base["Normal"], fontName=font, fontSize=9,
            textColor=colors.HexColor("#718096"), alignment=TA_CENTER,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontName=font, fontSize=9,
            leading=12, textColor=C_TEXT, wordWrap="CJK",
        ),
        "table_hdr": ParagraphStyle(
            "table_hdr", parent=base["Normal"], fontName=bold, fontSize=9,
            leading=11, textColor=C_HEADER_TEXT,
        ),
        "cell_count": ParagraphStyle(
            "cell_count", parent=base["Normal"], fontName=font, fontSize=9,
            leading=12, textColor=C_TEXT, alignment=TA_RIGHT,
        ),
    }


def _make_count_bar(count: int, max_count: int, color: colors.Color) -> Drawing:
    fill_w = int((count / max_count) * _BAR_WIDTH) if max_count > 0 else 0
    drawing = Drawing(_BAR_WIDTH, _BAR_HEIGHT)
    drawing.add(Rect(0, 0, _BAR_WIDTH, _BAR_HEIGHT, fillColor=_BAR_BG, strokeColor=None))
    if fill_w > 0:
        drawing.add(Rect(0, 0, fill_w, _BAR_HEIGHT, fillColor=color, strokeColor=None))
    return drawing


def _ml_col_widths(total_width: float) -> list[float]:
    ratio_sum = sum(_ML_COL_RATIOS)
    return [total_width * r / ratio_sum for r in _ML_COL_RATIOS]


def _cover(report: AnalystReport, styles: dict, width: float, meta: dict) -> list:
    header = Table(
        [
            [Paragraph("🐾  QA Release Report", styles["cover_title"])],
            [Paragraph(escape(meta["product"]), styles["cover_title"])],
            [Paragraph(meta["date_short"], styles["cover_title"])],
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

    env = Paragraph(
        f"TEST {report.test_unique_count} &nbsp;•&nbsp; "
        f"STAGE {report.stage_unique_count} &nbsp;•&nbsp; Общих {report.shared_count}",
        styles["body"],
    )
    return [header, Spacer(1, 5 * mm), banner, Spacer(1, 5 * mm), tiles, Spacer(1, 4 * mm), env]


def new_issues_flow(
    items: list,
    *,
    is_first_run: bool,
    styles: dict,
    width: float,
) -> list:
    flow = [Paragraph("🆕 НОВЫЕ ЛОГИ", styles["section"]), HRFlowable(width="100%", thickness=1, color=C_DIVIDER)]
    if is_first_run:
        flow.append(Paragraph("Первый запуск — снапшот сохранён. Новые логи в следующем отчёте.", styles["body"]))
        return flow

    if not items:
        flow.append(Paragraph("✅ Новых логов нет — всё уже было известно.", styles["body"]))
        return flow

    for item in items[:12]:
        flow.append(
            KeepTogether([
                _simple_card(
                    item.tracker_title,
                    f"{item.severity.value.upper()} | {item.environment} | count={item.issue.count}",
                    item.deploy_hint,
                    styles,
                    width,
                    stripe=colors.HexColor("#3182CE"),
                    bg=colors.HexColor("#EBF8FF"),
                )
            ])
        )
        flow.append(Spacer(1, 2 * mm))
    return flow


def _new_issues_page(report: AnalystReport, styles: dict, width: float) -> list:
    return new_issues_flow(
        report.new_issues_stage + report.new_issues_test,
        is_first_run=report.is_first_run,
        styles=styles,
        width=width,
    )


def blockers_high_flow(
    blockers: list[IssueRecord],
    highs: list[IssueRecord],
    styles: dict,
    width: float,
    *,
    empty_message: str = "Нет blocker/high.",
) -> list:
    issues = [(i, IssueSeverity.BLOCKER) for i in blockers] + [
        (i, IssueSeverity.HIGH) for i in highs
    ]
    if not issues:
        return [Paragraph(empty_message, styles["body"])]

    flow = [Paragraph("🔴 БЛОКЕРЫ И 🟠 HIGH", styles["section"]), HRFlowable(width="100%", thickness=1, color=C_DIVIDER)]
    for issue, sev in issues:
        flow.append(_issue_card(issue, sev, styles, width))
        flow.append(Spacer(1, 3 * mm))
    return flow


def _blockers_high(report: AnalystReport, styles: dict, width: float) -> list:
    return blockers_high_flow(
        report.blockers,
        report.highs,
        styles,
        width,
        empty_message="Нет blocker/high на stage.",
    )


def _issue_card(issue: IssueRecord, severity: IssueSeverity, styles: dict, width: float) -> KeepTogether:
    analysis = analyze_issue_full(issue, severity)
    stripe, bg, label = SEV_STYLE[severity]
    if analysis.is_stale:
        bg = C_STALE_BG
        stale_row = Table(
            [[Paragraph("УСТАРЕЛО", styles["stale_badge"])]],
            colWidths=[width - 6],
        )
        stale_row.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E2E8F0"))]))
    else:
        stale_row = Spacer(1, 0.1)

    badges = Table(
        [[
            Paragraph(f"count: {issue.count}", styles["small"]),
            Paragraph(f"last: {_fmt_short(issue.last_seen)}", styles["small"]),
        ]],
        colWidths=[(width - 6) / 2] * 2,
    )
    badges.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), C_BADGE_COUNT),
            ("BACKGROUND", (1, 0), (1, 0), C_BADGE_DATE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )

    body_html = (
        f"<b>{escape(analysis.tracker_title)}</b><br/><br/>"
        + format_analysis_plain(analysis)
    )
    inner = Table(
        [[Paragraph(f"● {label}  id={issue.id}", styles["card_title"])], [Paragraph(body_html, styles["body"])], [badges]],
        colWidths=[width - 6],
    )
    inner.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )

    if analysis.is_stale:
        rows = [[inner], [stale_row]]
    else:
        rows = [[inner]]

    body_wrap = Table(rows, colWidths=[width - 4])
    outer = Table([["", body_wrap]], colWidths=[4, width - 4])
    outer.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), stripe if not analysis.is_stale else colors.HexColor("#A0AEC0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    return KeepTogether([outer])


def _simple_card(
    title: str,
    meta: str,
    hint: str,
    styles: dict,
    width: float,
    *,
    stripe: colors.Color,
    bg: colors.Color,
) -> Table:
    inner = Table(
        [
            [Paragraph(escape(title), styles["card_title"])],
            [Paragraph(escape(meta), styles["small"])],
            [Paragraph(escape(hint), styles["small"])],
        ],
        colWidths=[width - 6],
    )
    inner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    outer = Table([["", inner]], colWidths=[4, width - 4])
    outer.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), stripe), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return outer


def _diff_regressions(report: AnalystReport, styles: dict, width: float) -> list:
    flow = [Paragraph("📊 ДИФФ И ⚠️ РЕГРЕССИИ", styles["section"]), HRFlowable(width="100%", thickness=1, color=C_DIVIDER)]

    if not report.is_tuesday_diff or not report.diff_available:
        flow.append(Paragraph("📌 Дифф появится со следующего вторника.", styles["body"]))
    elif report.diff_rows:
        data = [["Issue", "Было", "Сейчас", "Δ", "Статус"]]
        ts = [("BACKGROUND", (0, 0), (-1, 0), C_DIVIDER), ("GRID", (0, 0), (-1, -1), 0.25, C_DIVIDER), ("FONTSIZE", (0, 0), (-1, -1), 9)]
        for ri, row in enumerate(report.diff_rows[:30], 1):
            data.append([
                compact_text(row.title, max_len=40),
                str(row.prev_count if row.prev_count is not None else "—"),
                str(row.curr_count if row.curr_count is not None else "—"),
                row.delta_pct,
                row.status,
            ])
            if "новый" in row.status:
                ts.append(("LINEBEFORE", (0, ri), (0, ri), 3, colors.HexColor("#3182CE")))
            elif "исправлен" in row.status:
                ts.append(("TEXTCOLOR", (0, ri), (-1, ri), colors.HexColor("#38A169")))
        tbl = Table(data, colWidths=[width * 0.36, width * 0.12, width * 0.12, width * 0.12, width * 0.28])
        tbl.setStyle(TableStyle(ts))
        flow.append(tbl)
    else:
        flow.append(Paragraph("Изменений нет.", styles["body"]))

    flow.append(Spacer(1, 4 * mm))
    flow.append(Paragraph("⚠️ Регрессии", styles["section"]))
    if not report.regressions:
        flow.append(Paragraph("Нет активных регрессий.", styles["body"]))
    else:
        for issue in report.regressions[:12]:
            a = analyze_issue_full(issue, classify_severity(issue))
            flow.append(Paragraph(f"⚠️ РЕГРЕССИЯ: {escape(a.tracker_title)}", styles["body"]))
    return flow


def medium_low_table_flow(
    mediums: list[IssueRecord],
    lows: list[IssueRecord],
    *,
    env_label: str,
    styles: dict,
    width: float,
) -> list:
    rows_data = mediums + lows
    if not rows_data:
        return []

    medium_ids = {i.id for i in mediums}
    max_count = max((i.count for i in rows_data), default=1)
    font = styles["cell"].fontName
    col_widths = _ml_col_widths(width)
    flow = [Paragraph("🟡 MEDIUM / 🟢 LOW", styles["section"]), HRFlowable(width="100%", thickness=1, color=C_DIVIDER)]

    hdr = ["Уровень", "Модуль + название", "Частота", "Count", "Дата", "Env"]
    data: list[list] = [
        [Paragraph(escape(h), styles["table_hdr"]) for h in hdr],
    ]
    for issue in rows_data[:35]:
        sev = "MEDIUM" if issue.id in medium_ids else "LOW"
        title = analyze_issue_full(issue, classify_severity(issue)).tracker_title
        bar = _make_count_bar(issue.count, max_count, _BAR_COLORS[sev])
        data.append([
            sev,
            Paragraph(escape(title), styles["cell"]),
            bar,
            Paragraph(str(issue.count), styles["cell_count"]),
            _fmt_short(issue.last_seen),
            env_label,
        ])

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_HEADER_TEXT),
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("BACKGROUND", (5, 1), (5, -1), colors.HexColor("#EBF8FF")),
            ("TEXTCOLOR", (5, 1), (5, -1), colors.HexColor("#2B6CB0")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_DIVIDER),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#F0F0F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    flow.append(tbl)
    return flow


def _medium_low_table(report: AnalystReport, styles: dict, width: float) -> list:
    return medium_low_table_flow(
        report.mediums,
        report.lows,
        env_label="stage",
        styles=styles,
        width=width,
    )


def _fmt_short(dt: datetime) -> str:
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc)
    return f"{dt.day} {_MONTHS_RU[dt.month - 1]}"
