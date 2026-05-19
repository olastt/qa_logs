from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from qa_release_bot.issue_record import IssueRecord


class SnapshotStore:
    def __init__(self, directory: Path, *, retention_days: int = 60) -> None:
        self._dir = directory
        self._retention_days = retention_days
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, env: str, issues: list[IssueRecord], *, on_date: date | None = None) -> Path:
        day = on_date or datetime.now(timezone.utc).date()
        path = self._dir / f"{day.isoformat()}_{env}.json"
        payload = {
            "date": day.isoformat(),
            "env": env,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "issues": [i.to_snapshot_dict() for i in issues],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.prune_old()
        return path

    def load(self, env: str, on_date: date) -> list[IssueRecord] | None:
        path = self._dir / f"{on_date.isoformat()}_{env}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return [IssueRecord.from_snapshot_dict(i) for i in data.get("issues", [])]

    def load_previous_week(self, env: str, *, reference: date | None = None) -> list[IssueRecord] | None:
        """Снапшот на дату (reference - 7 дней)."""
        ref = reference or datetime.now(timezone.utc).date()
        return self.load(env, ref - timedelta(days=7))

    def load_previous_tuesday(self, env: str, *, reference: date | None = None) -> list[IssueRecord] | None:
        """Снапшот прошлого вторника для еженедельного диффа."""
        ref = reference or datetime.now(timezone.utc).date()
        tuesday = _previous_tuesday(ref)
        return self.load(env, tuesday)

    def load_latest_before(self, env: str, *, reference: date | None = None) -> list[IssueRecord] | None:
        """Последний снапшот до текущей даты (для сравнения «новых» id)."""
        ref = reference or datetime.now(timezone.utc).date()
        for d in sorted(self.list_dates(env), reverse=True):
            if d < ref:
                return self.load(env, d)
        return None


    def list_dates(self, env: str, *, limit: int = 56) -> list[date]:
        pattern = f"*_{env}.json"
        dates: list[date] = []
        for path in sorted(self._dir.glob(pattern), reverse=True):
            try:
                dates.append(date.fromisoformat(path.name.split("_")[0]))
            except ValueError:
                continue
            if len(dates) >= limit:
                break
        return dates

    def prune_old(self) -> int:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=self._retention_days)
        removed = 0
        for path in self._dir.glob("*.json"):
            try:
                file_date = date.fromisoformat(path.name.split("_")[0])
            except ValueError:
                continue
            if file_date < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed


def _previous_tuesday(ref: date) -> date:
    days_since = (ref.weekday() - 1) % 7
    if days_since == 0:
        days_since = 7
    return ref - timedelta(days=days_since)
