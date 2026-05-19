from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from qa_release_bot.html_dates import fmt_date_ru, fmt_date_ru_short, fmt_datetime_ru
from collections import defaultdict

from qa_release_bot.issue_analysis import IssueAnalysisFull, analyze_issue_full
from qa_release_bot.issue_titles import IssueTitleRegistry
from qa_release_bot.module_map import collect_unmapped_controllers
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.markdown_report import AnalystReport
from qa_release_bot.new_issues import NewIssueItem
from qa_release_bot.noise_groups import GroupedNoise
from qa_release_bot.release_decision import ReleaseDecision
from qa_release_bot.severity_rules import IssueSeverity, classify_severity
from qa_release_bot.snapshot_store import SnapshotStore
from qa_release_bot.summary_report import SummaryReport
from qa_release_bot.tuesday_diff import DiffRow

_SEV = {
    IssueSeverity.BLOCKER: ("BLOCKER", "red", "#f96b6b"),
    IssueSeverity.HIGH: ("HIGH", "amber", "#f5a623"),
    IssueSeverity.MEDIUM: ("MEDIUM", "purple", "#a78bfa"),
    IssueSeverity.LOW: ("LOW", "green", "#3ecf8e"),
}

_VERDICT = {
    "forbidden": ("verdict-forbidden", "🚫 РЕЛИЗ ЗАПРЕЩЁН"),
    "risk": ("verdict-risk", "⚠️ РЕЛИЗ С РИСКОМ"),
    "ok": ("verdict-ok", "✅ РЕЛИЗ ОК"),
}

_CSS = """
:root {
  --bg: #0e0f14;
  --surface: #16181f;
  --surface2: #1e2029;
  --border: rgba(255,255,255,0.07);
  --text: #f0f1f5;
  --muted: #7b7f91;
  --accent: #5b6af0;
  --green: #3ecf8e;
  --red: #f96b6b;
  --amber: #f5a623;
  --purple: #a78bfa;
  --teal: #2dd4bf;
  --radius: 14px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Onest', system-ui, sans-serif;
  font-weight: 400;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  min-height: 100vh;
}
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(91,106,240,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(91,106,240,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
  z-index: 0;
}
.wrap {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 24px 48px;
}
h1, h2, h3, .font-display { font-family: 'Unbounded', sans-serif; font-weight: 700; }
.section { margin-top: 36px; }
.section-title {
  font-family: 'Unbounded', sans-serif;
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 16px;
  letter-spacing: 0.02em;
}
.stub-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px 28px;
  color: var(--muted);
  font-size: 14px;
}
.header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
}
.header-title {
  font-size: 26px;
  background: linear-gradient(135deg, #fff 30%, #5b6af0);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.header-sub { color: var(--muted); font-size: 14px; margin-top: 6px; }
.badge-period {
  display: inline-block;
  padding: 8px 18px;
  background: rgba(91,106,240,0.15);
  border: 1px solid rgba(91,106,240,0.3);
  border-radius: 30px;
  font-size: 13px;
  color: #818cf8;
  white-space: nowrap;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}
@media (max-width: 900px) {
  .metrics { grid-template-columns: repeat(2, 1fr); }
}
.metric {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 16px 14px;
  border-top: 2px solid var(--metric-stripe, var(--accent));
  transition: border-color 0.2s;
}
.metric:hover { border-color: rgba(91,106,240,0.35); }
.metric-num {
  font-family: 'Unbounded', sans-serif;
  font-size: 32px;
  line-height: 1.1;
  color: var(--metric-color, var(--text));
}
.metric-lbl {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-top: 6px;
}
.verdict-banner {
  font-family: 'Unbounded', sans-serif;
  font-size: 22px;
  padding: 20px 28px;
  border-radius: var(--radius);
  margin-bottom: 12px;
}
.verdict-forbidden {
  background: rgba(249,107,107,0.12);
  border: 1px solid rgba(249,107,107,0.3);
  color: var(--red);
}
.verdict-risk {
  background: rgba(245,166,35,0.12);
  border: 1px solid rgba(245,166,35,0.3);
  color: var(--amber);
}
.verdict-ok {
  background: rgba(62,207,142,0.12);
  border: 1px solid rgba(62,207,142,0.3);
  color: var(--green);
}
.verdict-items {
  list-style: none;
  padding: 0 4px 8px;
  color: var(--muted);
  font-size: 13px;
}
.verdict-items li { margin: 4px 0; padding-left: 14px; position: relative; }
.verdict-items li::before { content: '•'; position: absolute; left: 0; }
.new-section { border-left: 3px solid var(--accent); padding-left: 20px; }
.new-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  margin-bottom: 12px;
}
.new-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  margin-bottom: 8px;
}
.new-title { font-weight: 500; font-size: 14px; margin-bottom: 6px; }
.new-meta { font-size: 12px; color: var(--muted); }
.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.issue-title-link {
  color: var(--text);
  text-decoration: none;
  border-bottom: 1px solid rgba(91,106,240,0.45);
  font-weight: 500;
}
.issue-title-link:hover { color: var(--accent); border-bottom-color: var(--accent); }
.ml-title a.issue-title-link { color: inherit; }
@media (max-width: 960px) {
  .charts-grid { grid-template-columns: 1fr; }
}
.chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  min-height: 260px;
  display: flex;
  flex-direction: column;
}
.chart-card h3 {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 12px;
}
.chart-wrap { flex: 1; position: relative; min-height: 200px; }
.issue-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 22px 18px 26px;
  margin-bottom: 16px;
  border-left: 4px solid var(--card-stripe, var(--red));
  position: relative;
}
.issue-card.stale-card {
  border-left-color: var(--muted);
  color: var(--muted);
}
.issue-card.stale-card .issue-body,
.issue-card.stale-card .issue-meta { color: var(--muted); }
.stale-badge {
  position: absolute;
  top: 14px;
  right: 16px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  padding: 4px 10px;
  background: rgba(123,127,145,0.2);
  color: var(--muted);
  border-radius: 6px;
}
.issue-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding-right: 80px;
}
.sev-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: 0.04em;
}
.sev-red { background: rgba(249,107,107,0.15); color: var(--red); }
.sev-amber { background: rgba(245,166,35,0.15); color: var(--amber); }
.sev-purple { background: rgba(167,139,250,0.15); color: var(--purple); }
.sev-green { background: rgba(62,207,142,0.15); color: var(--green); }
.issue-id { font-size: 12px; color: var(--muted); }
.dyn-badge {
  margin-left: auto;
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 20px;
}
.dyn-red { background: rgba(249,107,107,0.15); color: var(--red); }
.dyn-amber { background: rgba(245,166,35,0.15); color: var(--amber); }
.dyn-green { background: rgba(62,207,142,0.15); color: var(--green); }
.dyn-muted { background: rgba(123,127,145,0.15); color: var(--muted); }
.issue-tracker {
  font-family: 'Unbounded', sans-serif;
  font-size: 14px;
  margin-bottom: 14px;
  line-height: 1.45;
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: normal;
}
.issue-block { font-size: 13px; margin-bottom: 10px; }
.issue-block strong { color: var(--text); font-weight: 500; }
.issue-questions { margin: 8px 0 12px 18px; font-size: 13px; color: var(--muted); }
.issue-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
}
.bar-track {
  height: 8px;
  background: rgba(255,255,255,0.07);
  border-radius: 4px;
  overflow: hidden;
  margin-top: 4px;
}
.bar-fill { height: 100%; border-radius: 4px; }
.bar-label { font-size: 11px; color: var(--muted); margin-top: 4px; }
.ml-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.ml-table th {
  background: var(--surface2);
  text-align: left;
  padding: 12px 14px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  font-weight: 600;
}
.ml-table td { padding: 12px 14px; border-top: 1px solid var(--border); vertical-align: middle; }
.ml-table tbody tr:nth-child(even) { background: rgba(255,255,255,0.02); }
.ml-table tbody tr:hover { background: rgba(255,255,255,0.03); }
.ml-bar-track { height: 6px; background: rgba(255,255,255,0.07); border-radius: 3px; min-width: 80px; }
.ml-bar-fill { height: 100%; border-radius: 3px; }
.env-badge {
  display: inline-block;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
}
.env-stage { background: rgba(91,106,240,0.15); color: #818cf8; }
.env-test { background: rgba(167,139,250,0.15); color: #a78bfa; }
.diff-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.diff-table th {
  background: var(--surface2);
  text-align: left;
  padding: 10px 12px;
  font-size: 11px;
  color: var(--muted);
}
.diff-table td { padding: 10px 12px; border-top: 1px solid var(--border); }
.diff-table tr.diff-new { border-left: 3px solid var(--accent); }
.diff-table tr.diff-gone { opacity: 0.5; }
.diff-table tr.diff-gone td:first-child { text-decoration: line-through; }
.diff-table tr.diff-up { border-left: 3px solid var(--red); }
.diff-table tr.diff-up .diff-delta { color: var(--red); }
.diff-table tr.diff-down { border-left: 3px solid var(--green); }
.diff-table tr.diff-down .diff-delta { color: var(--green); }
.noise-list { list-style: none; }
.noise-list li {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 18px;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.noise-count { font-family: 'Unbounded', sans-serif; font-size: 18px; color: var(--muted); }
.footer {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--muted);
  text-align: center;
}
.env-stats { font-size: 13px; color: var(--muted); margin-bottom: 8px; }
.glitchtip-link {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 8px;
  background: rgba(91,106,240,0.15);
  border: 1px solid rgba(91,106,240,0.3);
  color: #818cf8; font-size: 12px; text-decoration: none;
  transition: background .2s; margin-top: 10px;
}
.glitchtip-link:hover { background: rgba(91,106,240,0.28); }
.glitchtip-icon {
  color: #818cf8; text-decoration: none; font-size: 16px; font-weight: 600;
}
.glitchtip-icon:hover { color: #a5b4fc; }
.risk-badge {
  display: inline-block; font-size: 10px; font-weight: 600;
  padding: 3px 8px; border-radius: 6px; text-transform: uppercase;
}
.risk-critical { background: rgba(249,107,107,0.2); color: var(--red); }
.risk-medium { background: rgba(245,166,35,0.2); color: var(--amber); }
.risk-low { background: rgba(123,127,145,0.2); color: var(--muted); }
.days-fresh { color: var(--green); }
.days-mid { color: var(--amber); }
.days-old { color: var(--red); }
.ml-group { margin-bottom: 8px; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.ml-group summary {
  cursor: pointer; padding: 12px 16px; background: var(--surface);
  font-weight: 600; list-style: none;
}
.ml-group summary::-webkit-details-marker { display: none; }
.ml-group summary::before { content: '▶ '; color: var(--muted); font-size: 10px; }
.ml-group[open] summary::before { content: '▼ '; }
.ml-group table { margin: 0; border: none; border-radius: 0; }
.ml-subrow td { font-size: 12px; padding: 8px 12px; }
.module-map-block {
  margin-top: 36px; padding: 20px 24px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius);
}
.module-map-block h2 { font-size: 14px; margin-bottom: 12px; color: var(--muted); }
.module-map-block code { color: #a5b4fc; font-size: 12px; }
.module-map-line { font-family: monospace; font-size: 12px; color: var(--text); margin: 4px 0; }
"""


@dataclass(slots=True)
class HtmlPageContext:
    page_title: str
    product_name: str
    subtitle: str
    fetched_at: datetime
    stats_period: str
    issue_query: str
    decision: ReleaseDecision
    blockers: list[IssueRecord]
    highs: list[IssueRecord]
    mediums: list[IssueRecord]
    lows: list[IssueRecord]
    new_issues: list[NewIssueItem] = field(default_factory=list)
    is_first_run: bool = False
    diff_rows: list[DiffRow] = field(default_factory=list)
    diff_available: bool = False
    is_tuesday_diff: bool = True
    noise_groups: list[GroupedNoise] = field(default_factory=list)
    trend_labels: list[str] = field(default_factory=list)
    trend_values: list[int] = field(default_factory=list)
    env_label: str = "stage"
    show_env_stats: bool = False
    test_unique_count: int = 0
    stage_unique_count: int = 0
    shared_count: int = 0
    total_api: int | None = None
    show_diff: bool = True
    is_summary: bool = False
    glitchtip_base_url: str = ""
    glitchtip_org_slug: str = ""
    glitchtip_project_id: str = ""


def default_analyst_html_path(output_dir: Path, fetched_at: datetime) -> Path:
    day = fetched_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return output_dir / f"qa_report_{day}.html"


def default_summary_html_path(output_dir: Path, report: SummaryReport) -> Path:
    day = report.fetched_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    slug = report.project_slug.replace("/", "-")
    return output_dir / f"summary_{slug}_{day}.html"


def build_analyst_html_context(
    report: AnalystReport,
    store: SnapshotStore | None = None,
    *,
    trend_env: str = "stage",
    glitchtip_base_url: str = "",
    glitchtip_org_slug: str = "",
) -> HtmlPageContext:
    labels, values = [], []
    if store:
        labels, values = _weekly_totals(store, trend_env)
    return HtmlPageContext(
        page_title="QA Release Report",
        product_name=report.product_name,
        subtitle=f"{report.product_name} · {fmt_date_ru_short(report.fetched_at)}",
        fetched_at=report.fetched_at,
        stats_period=report.stats_period,
        issue_query=report.issue_query,
        decision=report.decision,
        blockers=report.blockers,
        highs=report.highs,
        mediums=report.mediums,
        lows=report.lows,
        new_issues=report.new_issues_stage + report.new_issues_test,
        is_first_run=report.is_first_run,
        diff_rows=report.diff_rows,
        diff_available=report.diff_available,
        is_tuesday_diff=report.is_tuesday_diff,
        noise_groups=report.noise_groups,
        trend_labels=labels,
        trend_values=values,
        env_label="stage",
        show_env_stats=True,
        test_unique_count=report.test_unique_count,
        stage_unique_count=report.stage_unique_count,
        shared_count=report.shared_count,
        glitchtip_base_url=glitchtip_base_url.rstrip("/"),
        glitchtip_org_slug=glitchtip_org_slug,
    )


def build_summary_html_context(
    report: SummaryReport,
    store: SnapshotStore | None = None,
    *,
    glitchtip_base_url: str = "",
    glitchtip_org_slug: str = "",
) -> HtmlPageContext:
    return HtmlPageContext(
        page_title="Сводка логов",
        product_name=report.product_name,
        subtitle=(
            f"{report.instance} / {report.project_slug} · "
            f"{fmt_date_ru_short(report.fetched_at)}"
        ),
        fetched_at=report.fetched_at,
        stats_period=report.stats_period,
        issue_query=report.issue_query,
        decision=report.decision,
        blockers=report.blockers,
        highs=report.highs,
        mediums=report.mediums,
        lows=report.lows,
        new_issues=report.new_issues,
        is_first_run=report.is_first_run,
        noise_groups=report.noise_groups,
        env_label="test",
        total_api=report.total_unresolved,
        show_diff=False,
        is_summary=True,
        glitchtip_base_url=glitchtip_base_url.rstrip("/"),
        glitchtip_org_slug=glitchtip_org_slug,
        glitchtip_project_id=report.project_id,
    )


def write_analyst_html(
    report: AnalystReport,
    path: Path,
    *,
    store: SnapshotStore | None = None,
    glitchtip_base_url: str = "",
    glitchtip_org_slug: str = "",
    registry: object | None = None,
) -> Path:
    from qa_release_bot.issue_titles import IssueTitleRegistry

    ctx = build_analyst_html_context(
        report,
        store,
        glitchtip_base_url=glitchtip_base_url,
        glitchtip_org_slug=glitchtip_org_slug,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    reg = registry if isinstance(registry, IssueTitleRegistry) else IssueTitleRegistry()
    path.write_text(render_html(ctx, registry=reg), encoding="utf-8")
    return path


def write_summary_html(
    report: SummaryReport,
    path: Path,
    *,
    store: SnapshotStore | None = None,
    glitchtip_base_url: str = "",
    glitchtip_org_slug: str = "",
    registry: object | None = None,
) -> Path:
    from qa_release_bot.issue_titles import IssueTitleRegistry

    ctx = build_summary_html_context(
        report,
        store,
        glitchtip_base_url=glitchtip_base_url,
        glitchtip_org_slug=glitchtip_org_slug,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    reg = registry if isinstance(registry, IssueTitleRegistry) else IssueTitleRegistry()
    path.write_text(render_html(ctx, registry=reg), encoding="utf-8")
    return path


def format_html_message(path: Path) -> str:
    return f"✅ HTML сохранён: {path.resolve()}"


def _weekly_totals(store: SnapshotStore, env: str, weeks: int = 8) -> tuple[list[str], list[int]]:
    dates = sorted(store.list_dates(env, limit=weeks))
    if len(dates) < 2:
        return [], []
    labels = [fmt_date_ru(d) for d in dates]
    values = [sum(i.count for i in store.load(env, d) or []) for d in dates]
    return labels, values


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _strip_md(text: str) -> str:
    return text.replace("**", "")


def _all_issues(ctx: HtmlPageContext) -> list[tuple[IssueRecord, IssueSeverity]]:
    out: list[tuple[IssueRecord, IssueSeverity]] = []
    for issue in ctx.blockers:
        out.append((issue, IssueSeverity.BLOCKER))
    for issue in ctx.highs:
        out.append((issue, IssueSeverity.HIGH))
    for issue in ctx.mediums:
        out.append((issue, IssueSeverity.MEDIUM))
    for issue in ctx.lows:
        out.append((issue, IssueSeverity.LOW))
    return out


def _max_count(ctx: HtmlPageContext) -> int:
    counts = [i.count for i, _ in _all_issues(ctx)]
    return max(counts) if counts else 1


def _max_blocker_high_count(ctx: HtmlPageContext) -> int:
    counts = [i.count for i in ctx.blockers + ctx.highs]
    return max(counts) if counts else 1


def _max_ml_count(ctx: HtmlPageContext) -> int:
    counts = [i.count for i in ctx.mediums + ctx.lows]
    return max(counts) if counts else 1


def _dynamics_class(dynamics: str) -> str:
    if "STALE" in dynamics or "⚪" in dynamics:
        return "dyn-muted"
    if "🔴" in dynamics:
        return "dyn-red"
    if "🟢" in dynamics:
        return "dyn-green"
    return "dyn-amber"


def _dynamics_label(dynamics: str) -> str:
    if "STALE" in dynamics or "⚪" in dynamics:
        return "STALE"
    if "🔴" in dynamics:
        return "Активно растёт"
    if "🟢" in dynamics:
        return "Затухает"
    return "Хроническая"




def _progress_bar_html(pct: float, color: str, label: str = "") -> str:
    width = max(0.0, min(100.0, pct))
    lbl = f'<p class="bar-label">{_esc(label)}</p>' if label else ""
    return (
        f'<div class="bar-track"><div class="bar-fill" '
        f'style="width:{width:.1f}%;background:{color}"></div>'
        f"{lbl}"
    ).replace("", "")


def _diff_row_class(status: str) -> str:
    low = status.lower()
    if "новый" in low:
        return "diff-new"
    if "исправлен" in low:
        return "diff-gone"
    if "растёт" in low or "растет" in low:
        return "diff-up"
    if "падает" in low:
        return "diff-down"
    return ""


def _glitchtip_link_kwargs(ctx: HtmlPageContext) -> dict[str, str]:
    return {
        "glitchtip_base_url": ctx.glitchtip_base_url,
        "glitchtip_org_slug": ctx.glitchtip_org_slug,
        "glitchtip_project_id": ctx.glitchtip_project_id,
    }


def _warm_registry(ctx: HtmlPageContext, reg: IssueTitleRegistry) -> None:
    link = {**_glitchtip_link_kwargs(ctx), "summary_mode": ctx.is_summary}
    for issue in ctx.blockers:
        analyze_issue_full(
            issue, IssueSeverity.BLOCKER, registry=reg, **link
        )
    for issue in ctx.highs:
        analyze_issue_full(issue, IssueSeverity.HIGH, registry=reg, **link)
    for issue in ctx.mediums:
        analyze_issue_full(issue, IssueSeverity.MEDIUM, registry=reg, **link)
    for issue in ctx.lows:
        analyze_issue_full(issue, IssueSeverity.LOW, registry=reg, **link)
    for item in ctx.new_issues:
        analyze_issue_full(item.issue, item.severity, registry=reg, **link)


def _analyze(
    issue: IssueRecord,
    sev: IssueSeverity,
    ctx: HtmlPageContext,
    reg: IssueTitleRegistry,
) -> IssueAnalysisFull:
    return analyze_issue_full(
        issue,
        sev,
        registry=reg,
        summary_mode=ctx.is_summary,
        **_glitchtip_link_kwargs(ctx),
    )


def _glitchtip_link_html(url: str, *, compact: bool = False) -> str:
    if not url:
        return ""
    if compact:
        return (
            f'<a href="{_esc(url)}" target="_blank" class="glitchtip-icon" '
            f'title="Открыть в Glitchtip">↗</a>'
        )
    return (
        f'<a href="{_esc(url)}" target="_blank" class="glitchtip-link">'
        "🔗 Открыть в Glitchtip</a>"
    )


def _title_link_html(title: str, url: str) -> str:
    if url:
        return (
            f'<a href="{_esc(url)}" target="_blank" class="issue-title-link" '
            f'title="Открыть issue в Glitchtip">{_esc(title)}</a>'
        )
    return _esc(title)


def _risk_badge_html(risk_css: str, label: str) -> str:
    return f'<span class="risk-badge {risk_css}">{_esc(label)}</span>'


def _days_class(days: int) -> str:
    if days > 30:
        return "days-old"
    if days >= 7:
        return "days-mid"
    return "days-fresh"


def _top10_chart_data(
    ctx: HtmlPageContext,
    reg: IssueTitleRegistry,
) -> tuple[list[str], list[int], list[str]]:
    ranked = sorted(_all_issues(ctx), key=lambda p: -p[0].count)[:10]
    labels: list[str] = []
    values: list[int] = []
    colors: list[str] = []
    for issue, sev in ranked:
        a = _analyze(issue, sev, ctx, reg)
        title = a.tracker_title
        labels.append(title[:42] + ("…" if len(title) > 42 else ""))
        values.append(issue.count)
        colors.append(_SEV[sev][2])
    return labels, values, colors


def _env_badge(env: str) -> str:
    cls = "env-stage" if env == "stage" else "env-test"
    return f'<span class="env-badge {cls}">{_esc(env)}</span>'


def render_html(
    ctx: HtmlPageContext,
    registry: IssueTitleRegistry | None = None,
) -> str:
    fetched = ctx.fetched_at.astimezone(timezone.utc)
    total_product = len(ctx.blockers) + len(ctx.highs) + len(ctx.mediums) + len(ctx.lows)
    max_count = _max_blocker_high_count(ctx)
    reg = registry or IssueTitleRegistry()
    _warm_registry(ctx, reg)

    parts = [
        "<!DOCTYPE html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f"<title>{_esc(ctx.page_title)} — {_esc(ctx.product_name)}</title>",
        '<link rel="preconnect" href="https://fonts.googleapis.com"/>',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>',
        '<link href="https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600&family=Unbounded:wght@700&display=swap" rel="stylesheet"/>',
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>',
        "<style>",
        _CSS,
        "</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
        _header(ctx, fetched),
        _metrics(ctx, total_product),
        _verdict(ctx) if not ctx.is_summary else _summary_intro(ctx),
        _new_issues_section(ctx, reg),
        _charts_section(ctx, reg),
        _blockers_high_section(ctx, max_count, reg),
        _medium_low_section(ctx, reg),
        _diff_section(ctx),
        _noise_section(ctx),
        _module_map_section(ctx),
        _footer(ctx, fetched),
        "</div>",
        "<script>",
        _charts_js(ctx, reg),
        "</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


def _header(ctx: HtmlPageContext, fetched: datetime) -> str:
    period_badge = f"{fmt_date_ru_short(fetched)} · {_esc(ctx.stats_period)} · {_esc(ctx.issue_query)}"
    env_line = ""
    if ctx.show_env_stats:
        env_line = (
            f'<p class="env-stats">TEST: {ctx.test_unique_count} · '
            f"STAGE: {ctx.stage_unique_count} · Общих: {ctx.shared_count}</p>"
        )
    elif ctx.total_api is not None:
        env_line = f'<p class="env-stats">Всего unresolved (API): {ctx.total_api}</p>'
    return f"""<header class="header">
  <div>
    <h1 class="header-title">{_esc(ctx.page_title)}</h1>
    <p class="header-sub">{_esc(ctx.subtitle)}</p>
    {env_line}
  </div>
  <span class="badge-period">{period_badge}</span>
</header>"""


def _metrics(ctx: HtmlPageContext, total: int) -> str:
    tiles = [
        (len(ctx.blockers), "🔴 BLOCKER", "#f96b6b", "#f96b6b"),
        (len(ctx.highs), "🟠 HIGH", "#f5a623", "#f5a623"),
        (len(ctx.mediums), "🟡 MEDIUM", "#a78bfa", "#a78bfa"),
        (len(ctx.lows), "🟢 LOW", "#3ecf8e", "#3ecf8e"),
        (total, "⚪ ВСЕГО", "#5b6af0", "#818cf8"),
    ]
    cards = []
    for num, lbl, stripe, color in tiles:
        cards.append(
            f'<div class="metric" style="--metric-stripe:{stripe};--metric-color:{color}">'
            f'<p class="metric-num">{num}</p><p class="metric-lbl">{_esc(lbl)}</p></div>'
        )
    return f'<section class="metrics">{"".join(cards)}</section>'


def _summary_intro(ctx: HtmlPageContext) -> str:
    headline = _strip_md(ctx.decision.headline)
    items = "".join(
        f"<li>{_esc(_strip_md(item))}</li>" for item in ctx.decision.items[:8]
    )
    list_html = f'<ul class="verdict-items">{items}</ul>' if items else ""
    return f"""<section class="section">
  <div class="verdict-banner verdict-ok">{_esc(headline)}
  {list_html}
  </div>
</section>"""


def _verdict(ctx: HtmlPageContext) -> str:
    css_cls, title = _VERDICT.get(ctx.decision.verdict, _VERDICT["ok"])
    items = "".join(
        f"<li>{_esc(_strip_md(item))}</li>" for item in ctx.decision.items[:12]
    )
    list_html = f'<ul class="verdict-items">{items}</ul>' if items else ""
    return f"""<section class="section">
  <div class="verdict-banner {css_cls}">{_esc(title)}
  {list_html}
  </div>
</section>"""


def _new_issues_section(ctx: HtmlPageContext, reg: IssueTitleRegistry) -> str:
    if ctx.is_summary:
        return _new_issues_section_summary(ctx, reg)
    if ctx.is_first_run:
        body = (
            '<p class="stub-card">📌 <strong>Первый запуск.</strong> Снапшот сохранён. '
            "Новые логи появятся в следующем отчёте.</p>"
        )
        section_title = "🆕 Новые логи"
        return f'<section class="section"><h2 class="section-title">{section_title}</h2>{body}</section>'
    if not ctx.new_issues:
        empty = (
            "✅ <strong>Новых логов за сегодня нет</strong>."
            if ctx.is_summary
            else "✅ <strong>Новых логов нет</strong> — всё уже было известно."
        )
        note = (
            '<p class="stub-card" style="margin-bottom:12px">'
            "Логи с <strong>first_seen</strong> за сегодня (МСК) по всем issue проекта.</p>"
            if ctx.is_summary
            else ""
        )
        body = f"{note}<p class=\"stub-card\">{empty}</p>"
    else:
        note = (
            '<p class="stub-card" style="margin-bottom:12px">'
            "Логи с <strong>first_seen</strong> за сегодня (МСК) по всем issue проекта.</p>"
            if ctx.is_summary
            else ""
        )
        cards = []
        for item in ctx.new_issues[:25]:
            a = _analyze(item.issue, item.severity, ctx, reg)
            sev_label, _, _ = _SEV[item.severity]
            first = fmt_date_ru(item.issue.first_seen)
            link = _glitchtip_link_html(a.glitchtip_url)
            module_line = (
                f'<p class="new-meta"><strong>Модуль:</strong> {_esc(a.module)}</p>'
                if ctx.is_summary and a.module
                else ""
            )
            what_block = (
                f'<p class="issue-block"><strong>🔍 Что случилось:</strong> '
                f"{_esc(a.what_happened)}</p>"
                if ctx.is_summary
                else ""
            )
            title = (
                f'<p class="new-title">{_title_link_html(a.tracker_title, a.glitchtip_url)}</p>'
                if ctx.is_summary
                else f'<p class="new-title">{_esc(a.tracker_title)}</p>'
            )
            badge = "СЕГОДНЯ" if ctx.is_summary else "НОВОЕ"
            cards.append(
                f'<div class="new-card">'
                f'<span class="new-badge">{badge}</span>'
                f"{title}"
                f'<p class="new-meta">{_esc(sev_label)} · {_esc(item.environment)} · '
                f"первый раз: {_esc(first)} · повторов: {item.issue.count}</p>"
                f'<p class="new-meta">{_esc(item.deploy_hint)}</p>'
                f"{module_line}{what_block}"
                f"{'' if ctx.is_summary else link}"
                f"</div>"
            )
        rest = len(ctx.new_issues) - min(25, len(ctx.new_issues))
        more = f'<p class="new-meta">… ещё {rest}</p>' if rest > 0 else ""
        body = f'{note}<div class="new-section">{"".join(cards)}{more}</div>'
    section_title = "🆕 Новые логи"
    return f'<section class="section"><h2 class="section-title">{section_title}</h2>{body}</section>'


def _new_issues_section_summary(ctx: HtmlPageContext, reg: IssueTitleRegistry) -> str:
    note = (
        '<p class="stub-card" style="margin-bottom:12px">'
        "Логи с <strong>first_seen</strong> за сегодня (МСК) по всем issue проекта."
    )
    if ctx.is_first_run:
        note += " Снапшот для динамики сохранён."
    note += "</p>"

    if not ctx.new_issues:
        body = f'{note}<p class="stub-card">✅ <strong>Новых логов за сегодня нет</strong>.</p>'
    else:
        max_count = max((i.issue.count for i in ctx.new_issues), default=1)
        cards = "".join(
            _issue_card_html(item.issue, item.severity, max_count, ctx, reg)
            for item in ctx.new_issues[:25]
        )
        rest = len(ctx.new_issues) - min(25, len(ctx.new_issues))
        more = f'<p class="stub-card">… ещё {rest}</p>' if rest > 0 else ""
        body = f"{note}{cards}{more}"
    return (
        '<section class="section">'
        '<h2 class="section-title">🆕 Новые логи за сегодня</h2>'
        f"{body}</section>"
    )


def _charts_section(ctx: HtmlPageContext, reg: IssueTitleRegistry) -> str:
    return f"""<section class="section">
  <h2 class="section-title">📊 Графики</h2>
  <div class="charts-grid">
    <div class="chart-card">
      <h3>По уровням</h3>
      <div class="chart-wrap"><canvas id="chartSeverity"></canvas></div>
    </div>
    <div class="chart-card">
      <h3>Топ-10 по кол-ву</h3>
      <div class="chart-wrap"><canvas id="chartTop10"></canvas></div>
    </div>
  </div>
</section>"""


def _issue_card_html(
    issue: IssueRecord,
    sev: IssueSeverity,
    max_count: int,
    ctx: HtmlPageContext,
    reg: IssueTitleRegistry,
) -> str:
    analysis = _analyze(issue, sev, ctx, reg)
    label, tone, color = _SEV[sev]
    stale_cls = " stale-card" if analysis.is_stale else ""
    stripe = "var(--muted)" if analysis.is_stale else color
    stale_badge = '<span class="stale-badge">УСТАРЕЛО</span>' if analysis.is_stale else ""
    dyn_cls = _dynamics_class(analysis.history.dynamics)
    dyn_lbl = _dynamics_label(analysis.history.dynamics)
    pct = (issue.count / max_count * 100) if max_count else 0
    module_line = (
        f'<p class="issue-block"><strong>📍 Модуль:</strong> {_esc(analysis.module)}</p>'
        if analysis.module
        else ""
    )
    dev_block = ""
    user_block = (
        f'<p class="issue-block"><strong>💥 Что видит пользователь:</strong> '
        f"{_esc(analysis.user_visible)}</p>"
    )
    if not ctx.is_summary:
        if analysis.dev_hypothesis:
            dev_block = (
                f'<p class="issue-block"><strong>💡 Предположение:</strong> '
                f"{_esc(analysis.dev_hypothesis)}</p>"
            )
        elif analysis.dev_questions:
            q_html = "".join(f"<li>{_esc(q)}</li>" for q in analysis.dev_questions)
            dev_block = (
                '<p class="issue-block"><strong>❓ Уточнить у разработчика:</strong></p>'
                f'<ul class="issue-questions">{q_html}</ul>'
            )
    else:
        user_block = ""
    link = _glitchtip_link_html(analysis.glitchtip_url)
    history_line = _esc(
        f"Существует: {analysis.history.exists_days} дн. "
        f"(с {analysis.history.first_seen_label} → {analysis.history.last_seen_label})"
    )
    return f"""<article class="issue-card{stale_cls}" style="--card-stripe:{stripe}">
  {stale_badge}
  <div class="issue-head">
    <span class="sev-badge sev-{tone}">{_esc(label)}</span>
    <span class="issue-id">id={_esc(issue.id)}</span>
    <span class="dyn-badge {dyn_cls}">{_esc(dyn_lbl)}</span>
  </div>
  <p class="issue-tracker">{_title_link_html(analysis.tracker_title, analysis.glitchtip_url)}</p>
  <div class="issue-body">
    <p class="issue-block"><strong>🔍 Что случилось:</strong> {_esc(analysis.what_happened)}</p>
    {module_line}
    {user_block}
    <p class="issue-block"><strong>⚠️ Риск:</strong> {_risk_badge_html(analysis.risk_css, analysis.risk_label)}</p>
    {dev_block}
  </div>
  <p class="issue-meta">📅 {history_line} · {_esc(f"👁 {analysis.history.last_seen_label}")} · 🔁 {issue.count} повт.</p>
  {_progress_bar_html(pct, color, f"count: {issue.count}")}
  {link}
</article>"""


def _blockers_high_section(
    ctx: HtmlPageContext, max_count: int, reg: IssueTitleRegistry
) -> str:
    issues = [(i, IssueSeverity.BLOCKER) for i in ctx.blockers] + [
        (i, IssueSeverity.HIGH) for i in ctx.highs
    ]
    if not issues:
        body = (
            '<p class="stub-card">Нет активных blocker/high на '
            f"{_esc(ctx.env_label)} — отличная новость.</p>"
        )
    else:
        body = "".join(
            _issue_card_html(i, s, max_count, ctx, reg) for i, s in issues
        )
    return f"""<section class="section">
  <h2 class="section-title">🔴 Блокеры и 🟠 High</h2>
  {body}
</section>"""


def _truncate_display_title(title: str, max_len: int = 60) -> str:
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"


def _ml_table_row(
    issue: IssueRecord,
    sev: IssueSeverity,
    ctx: HtmlPageContext,
    reg: IssueTitleRegistry,
) -> str:
    analysis = _analyze(issue, sev, ctx, reg)
    label, tone, _ = _SEV[sev]
    title = _truncate_display_title(analysis.tracker_title)
    days = analysis.history.exists_days
    return (
        f"<tr>"
        f'<td><span class="sev-badge sev-{tone}">{_esc(label)}</span></td>'
        f'<td class="ml-title">{_title_link_html(title, analysis.glitchtip_url)}</td>'
        f"<td>{_risk_badge_html(analysis.risk_css, analysis.risk_label)}</td>"
        f"<td>{issue.count}</td>"
        f"<td>{_esc(fmt_date_ru(issue.first_seen))}</td>"
        f"<td>{_esc(fmt_datetime_ru(issue.last_seen))}</td>"
        f'<td class="{_days_class(days)}">{days}</td>'
        f"<td>{_env_badge(ctx.env_label)}</td>"
        f"<td>{_glitchtip_link_html(analysis.glitchtip_url, compact=True)}</td>"
        f"</tr>"
    )


def _medium_low_section(ctx: HtmlPageContext, reg: IssueTitleRegistry) -> str:
    rows_issues = [(i, IssueSeverity.MEDIUM) for i in ctx.mediums] + [
        (i, IssueSeverity.LOW) for i in ctx.lows
    ]
    if not rows_issues:
        return """<section class="section">
  <h2 class="section-title">🟡 Medium / 🟢 Low</h2>
  <p class="stub-card">Нет medium/low — таблица пуста.</p>
</section>"""
    from collections import defaultdict

    groups: dict[str, list[tuple[IssueRecord, IssueSeverity]]] = defaultdict(list)
    for issue, sev in rows_issues:
        tag = _analyze(issue, sev, ctx, reg).group_tag
        groups[tag].append((issue, sev))

    body_rows: list[str] = []
    for tag in sorted(groups.keys(), key=lambda t: (-len(groups[t]), t)):
        items = sorted(groups[tag], key=lambda p: -p[0].count)
        if len(items) == 1:
            body_rows.append(_ml_table_row(items[0][0], items[0][1], ctx, reg))
            continue
        inner = "".join(_ml_table_row(i, s, ctx, reg) for i, s in items)
        body_rows.append(
            f'<tr class="ml-group-row"><td colspan="9">'
            f'<details class="ml-group">'
            f'<summary><span class="ml-group-tag">[{_esc(tag)}]</span>'
            f" — {len(items)} issues</summary>"
            f'<table class="ml-table ml-nested"><tbody>{inner}</tbody></table>'
            f"</details></td></tr>"
        )

    table = f"""<table class="ml-table">
  <thead><tr>
    <th>Уровень</th><th>Название</th><th>Риск</th><th>Кол-во</th>
    <th>Впервые</th><th>Последний</th><th>Дней</th><th>Env</th><th></th>
  </tr></thead>
  <tbody>{"".join(body_rows)}</tbody>
</table>"""
    return f"""<section class="section">
  <h2 class="section-title">🟡 Medium / 🟢 Low</h2>
  {table}
</section>"""



def _module_map_section(ctx: HtmlPageContext) -> str:
    issues = [issue for issue, _ in _all_issues(ctx)]
    unmapped = collect_unmapped_controllers(issues)
    if not unmapped:
        return ""
    lines = "".join(
        f'<p class="module-map-line"><code>{_esc(ctrl)}</code> — {_esc(desc)}</p>'
        for ctrl, desc in unmapped
    )
    return f"""<section class="module-map-block">
  <h2>🗺️ Неизвестные модули (ExtJS)</h2>
  <p>Контроллеры в стеке, которых ещё нет в <code>config/module_map.yaml</code>. После добавления в отчёте появятся понятные названия разделов.</p>
  {lines}
</section>"""

def _diff_section(ctx: HtmlPageContext) -> str:
    if not ctx.show_diff:
        return ""
    if ctx.is_first_run or not ctx.diff_available or not ctx.is_tuesday_diff:
        return """<section class="section">
  <h2 class="section-title">📊 Дифф с прошлым вторником</h2>
  <p class="stub-card">📌 Первый запуск — дифф появится со следующего вторника
  (нужен снапшот прошлого вторника).</p>
</section>"""
    if not ctx.diff_rows:
        return """<section class="section">
  <h2 class="section-title">📊 Дифф с прошлым вторником</h2>
  <p class="stub-card">Изменений с прошлого вторника нет.</p>
</section>"""
    rows = []
    for row in ctx.diff_rows[:40]:
        cls = _diff_row_class(row.status)
        prev = str(row.prev_count) if row.prev_count is not None else "—"
        curr = str(row.curr_count) if row.curr_count is not None else "—"
        rows.append(
            f'<tr class="{cls}">'
            f"<td>{_esc(row.title)}</td>"
            f"<td>{_esc(prev)}</td><td>{_esc(curr)}</td>"
            f'<td class="diff-delta">{_esc(row.delta_pct)}</td>'
            f"<td>{_esc(row.status)}</td></tr>"
        )
    table = f"""<table class="diff-table">
  <thead><tr>
    <th>Issue</th><th>Прошлая неделя</th><th>Эта неделя</th><th>Δ</th><th>Статус</th>
  </tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""
    return f"""<section class="section">
  <h2 class="section-title">📊 Дифф с прошлым вторником</h2>
  {table}
</section>"""


def _noise_section(ctx: HtmlPageContext) -> str:
    if not ctx.noise_groups:
        return ""
    items = "".join(
        f"<li><span>{_esc(g.label)}</span>"
        f'<span class="noise-count">{g.total_count}</span></li>'
        for g in ctx.noise_groups
    )
    return f"""<section class="section">
  <h2 class="section-title">🗑️ Шум (сгруппировано)</h2>
  <p class="stub-card" style="margin-bottom:12px">Типовые инфраструктурные ошибки, вынесенные из основной таблицы (file_put_contents, ClickHouse).</p>
  <ul class="noise-list">{items}</ul>
</section>"""


def _footer(ctx: HtmlPageContext, fetched: datetime) -> str:
    ts = fetched.strftime("%Y-%m-%d %H:%M UTC")
    date_ru = fmt_date_ru_short(fetched)
    return f"""<footer class="footer">
  {_esc(ctx.page_title)} · {_esc(ctx.product_name)} · {_esc(date_ru)} ·
  Данные: {_esc(ts)}
</footer>"""


def _charts_js(ctx: HtmlPageContext, reg: IssueTitleRegistry) -> str:
    sev_labels = ["BLOCKER", "HIGH", "MEDIUM", "LOW"]
    sev_values = [
        len(ctx.blockers),
        len(ctx.highs),
        len(ctx.mediums),
        len(ctx.lows),
    ]
    sev_colors = ["#f96b6b", "#f5a623", "#a78bfa", "#3ecf8e"]
    top_labels, top_values, top_colors = _top10_chart_data(ctx, reg)

    tooltip = {
        "backgroundColor": "#1e2029",
        "titleColor": "#f0f1f5",
        "bodyColor": "#7b7f91",
        "borderColor": "rgba(255,255,255,0.1)",
        "borderWidth": 1,
        "padding": 10,
        "cornerRadius": 8,
    }
    scale_opts = {
        "grid": {"color": "rgba(255,255,255,0.05)", "display": True},
        "ticks": {"color": "#7b7f91", "font": {"family": "Onest", "size": 11}},
        "border": {"display": False},
    }

    lines = [
        "document.addEventListener('DOMContentLoaded', function() {",
        "  const tooltip = " + json.dumps(tooltip, ensure_ascii=False) + ";",
        "  const scaleOpts = " + json.dumps(scale_opts, ensure_ascii=False) + ";",
        "",
        "  new Chart(document.getElementById('chartSeverity'), {",
        "    type: 'doughnut',",
        "    data: {",
        f"      labels: {json.dumps(sev_labels, ensure_ascii=False)},",
        "      datasets: [{",
        f"        data: {json.dumps(sev_values)},",
        f"        backgroundColor: {json.dumps(sev_colors)},",
        "        borderWidth: 0,",
        "      }],",
        "    },",
        "    options: {",
        "      cutout: '68%',",
        "      plugins: { legend: { display: false }, tooltip },",
        "    },",
        "  });",
        "",
        "  new Chart(document.getElementById('chartTop10'), {",
        "    type: 'bar',",
        "    data: {",
        f"      labels: {json.dumps(top_labels, ensure_ascii=False)},",
        "      datasets: [{",
        f"        data: {json.dumps(top_values)},",
        f"        backgroundColor: {json.dumps(top_colors)},",
        "        borderWidth: 0,",
        "      }],",
        "    },",
        "    options: {",
        "      indexAxis: 'y',",
        "      plugins: { legend: { display: false }, tooltip },",
        "      scales: { x: scaleOpts, y: { ...scaleOpts, grid: { display: false } } },",
        "    },",
        "  });",
    ]

    lines.append("});")
    return "\n".join(lines)
