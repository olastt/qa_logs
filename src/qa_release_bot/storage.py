from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class IssueStateStore:
    """Локальная память: какие issue id уже видели."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_issues (
                    instance TEXT NOT NULL,
                    project_slug TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (instance, project_slug, issue_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watched_new_issues (
                    instance TEXT NOT NULL,
                    project_slug TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (instance, project_slug, issue_id)
                )
                """
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def is_known(self, instance: str, project_slug: str, issue_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM seen_issues
                WHERE instance = ? AND project_slug = ? AND issue_id = ?
                """,
                (instance, project_slug, issue_id),
            ).fetchone()
        return row is not None

    def mark_seen(
        self,
        instance: str,
        project_slug: str,
        issue_id: str,
        *,
        seen_at: datetime | None = None,
    ) -> None:
        now = (seen_at or datetime.now(timezone.utc)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO seen_issues (instance, project_slug, issue_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(instance, project_slug, issue_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at
                """,
                (instance, project_slug, issue_id, now, now),
            )

    def filter_new(
        self,
        instance: str,
        project_slug: str,
        issue_ids: list[str],
    ) -> list[str]:
        return [iid for iid in issue_ids if not self.is_known(instance, project_slug, iid)]

    def watched_issue_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM watched_new_issues").fetchone()
        return int(row[0] if row else 0)

    def is_watched_issue_known(self, instance: str, project_slug: str, issue_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM watched_new_issues
                WHERE instance = ? AND project_slug = ? AND issue_id = ?
                """,
                (instance, project_slug, issue_id),
            ).fetchone()
        return row is not None

    def mark_watched_issue_seen(
        self,
        instance: str,
        project_slug: str,
        issue_id: str,
        *,
        seen_at: datetime | None = None,
    ) -> None:
        now = (seen_at or datetime.now(timezone.utc)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watched_new_issues (
                    instance, project_slug, issue_id, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(instance, project_slug, issue_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at
                """,
                (instance, project_slug, issue_id, now, now),
            )
