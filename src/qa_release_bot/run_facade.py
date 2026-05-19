"""Единая точка запуска release / summary для CLI и CI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from qa_release_bot.config import Settings, load_report_config, report_output_dir
from qa_release_bot.notify_format import format_release_notify, format_summary_notify
from qa_release_bot.projects import CliProject, get_cli_project, surge_domain
from qa_release_bot.qa_analyst_runner import QAAnalystRunner
from qa_release_bot.summary_runner import SingleProjectSummaryRunner


@dataclass(slots=True)
class RunResult:
    command: str
    project_id: str
    success: bool
    notify_text: str
    surge_domain: str
    html_glob: str
    html_path: str = ""


def run_release(
    project_id: str,
    settings: Settings | None = None,
    *,
    save_html: bool = True,
    no_stack: bool = True,
    print_console: bool = False,
) -> RunResult:
    project = get_cli_project(project_id)
    if project.kind != "release":
        raise ValueError(f"«{project_id}» — не release-проект. Используйте: qa-bot summary {project_id}")

    cfg = load_report_config()
    out_dir = Path(report_output_dir(cfg))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    md_path = out_dir / f"release-{project_id}-{stamp}.md"

    report = QAAnalystRunner(settings).run(
        project_name=project_id,
        save_markdown=md_path,
        save_html=save_html,
        save_pdf=False,
        print_console=print_console,
        enrich_stack=False if no_stack else None,
    )

    domain = surge_domain(project_id, "release")
    report_url = f"https://{domain}"
    notify = format_release_notify(project_id, report, report_url)
    html_path = _latest_html(out_dir, "qa_report_*.html")
    _write_ci_meta(
        out_dir,
        project_id=project_id,
        command="release",
        surge_domain=domain,
        notify_text=notify,
        html_path=str(html_path) if html_path else "",
        verdict=report.decision.verdict,
        blockers=len(report.blockers),
        highs=len(report.highs),
    )
    return RunResult(
        command="release",
        project_id=project_id,
        success=True,
        notify_text=notify,
        surge_domain=domain,
        html_glob="qa_report_*.html",
        html_path=str(html_path) if html_path else "",
    )


def run_summary(
    project_id: str,
    settings: Settings | None = None,
    *,
    save_html: bool = True,
    no_stack: bool = True,
    print_console: bool = False,
) -> RunResult:
    project = get_cli_project(project_id)
    if project.kind != "summary":
        raise ValueError(f"«{project_id}» — не summary. Используйте: qa-bot release {project_id}")

    cfg = load_report_config()
    out_dir = Path(report_output_dir(cfg))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    md_path = out_dir / f"summary-{project_id}-{stamp}.md"
    summary_name = project.summary_config_name or project_id

    summary = SingleProjectSummaryRunner(settings).run(
        name=summary_name,
        save_markdown=md_path,
        save_html=save_html,
        save_pdf=False,
        print_console=print_console,
        enrich_stack=False if no_stack else None,
    )

    domain = surge_domain(project_id, "summary")
    report_url = f"https://{domain}"
    notify = format_summary_notify(
        project_id,
        summary,
        disappeared_count=summary.disappeared_count,
        report_url=report_url,
    )
    html_glob = f"summary_*{summary.project_slug.replace('/', '-')}*.html"
    html_path = _latest_html(out_dir, html_glob) or _latest_html(out_dir, "summary_*.html")
    _write_ci_meta(
        out_dir,
        project_id=project_id,
        command="summary",
        surge_domain=domain,
        notify_text=notify,
        html_path=str(html_path) if html_path else "",
        new_issues=len(summary.new_issues),
        disappeared=summary.disappeared_count,
    )
    return RunResult(
        command="summary",
        project_id=project_id,
        success=True,
        notify_text=notify,
        surge_domain=domain,
        html_glob=html_glob,
        html_path=str(html_path) if html_path else "",
    )


def notify_with_url(notify_text: str, report_url: str) -> str:
    if not report_url:
        return notify_text
    if "👉 Отчёт:" in notify_text:
        lines = notify_text.splitlines()
        return "\n".join(
            line if not line.startswith("👉 Отчёт:") else f"👉 Отчёт: {report_url}"
            for line in lines
        )
    return f"{notify_text}\n👉 Отчёт: {report_url}"


def _latest_html(out_dir: Path, pattern: str) -> Path | None:
    files = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _write_ci_meta(out_dir: Path, *, project_id: str, **fields: object) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / f"ci_meta_{project_id}.json"
    meta_path.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "ci_meta.json").write_text(meta_path.read_text(encoding="utf-8"), encoding="utf-8")
    notify = str(fields.get("notify_text", ""))
    (out_dir / f"ci_message_{project_id}.txt").write_text(notify, encoding="utf-8")


def append_ci_message(out_dir: Path, lines: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = "\n\n".join(line for line in lines if line.strip())
    (out_dir / "ci_message.txt").write_text(text, encoding="utf-8")
