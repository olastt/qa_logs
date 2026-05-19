from __future__ import annotations

from datetime import date, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.noise_groups import _normalize_title
from qa_release_bot.tuesday_diff import DiffRow, is_recent


def find_regressions(
    stage: list[IssueRecord],
    test: list[IssueRecord],
    *,
    last_deploy: date | None,
    diff_rows: list[DiffRow],
) -> list[IssueRecord]:
    test_titles = {_normalize_title(i.title) for i in test}
    diff_by_title = {_normalize_title(r.title): r for r in diff_rows}
    result: list[IssueRecord] = []

    for issue in stage:
        key = _normalize_title(issue.title)
        reasons: list[str] = []

        if key not in test_titles:
            reasons.append("нет на TEST")
        if last_deploy and _first_seen_date(issue) > last_deploy:
            reasons.append("first_seen после деплоя")
        row = diff_by_title.get(key)
        if row and row.status in ("📈 растёт", "⚠️ регрессия", "🆕 новый"):
            reasons.append(f"динамика: {row.status}")
        if row and row.delta_pct.startswith("+") and row.prev_count:
            try:
                pct = float(row.delta_pct.strip("+%"))
                if pct > 100:
                    reasons.append("count +100% за неделю")
            except ValueError:
                pass

        if reasons and is_recent(issue):
            issue.metadata["_regression_reasons"] = reasons
            result.append(issue)

    return sorted(result, key=lambda i: -i.count)


def _first_seen_date(issue: IssueRecord) -> date:
    fs = issue.first_seen
    if fs.tzinfo:
        return fs.astimezone(timezone.utc).date()
    return fs.date()
