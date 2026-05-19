from __future__ import annotations

import structlog

from qa_release_bot.classifier import classify_group, classify_issue
from qa_release_bot.config import Settings, build_project_refs
from qa_release_bot.fetcher import fetch_all_issues
from qa_release_bot.grouper import group_issues
from qa_release_bot.models import NewIssueAlert
from qa_release_bot.notifier import Notifier
from qa_release_bot.storage import IssueStateStore

log = structlog.get_logger(__name__)


class QAReleaseBot:
    """Оркестратор одного цикла опроса."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store = IssueStateStore(settings.state_db_path)
        self._notifier = Notifier()
        self._projects = build_project_refs(settings)

    def run_once(self) -> None:
        log.info("poll_start", projects=len(self._projects))
        issues = fetch_all_issues(self._settings, self._projects)
        groups = group_issues(issues)

        alerts: list[NewIssueAlert] = []
        for issue in issues:
            key = (issue.project.instance, issue.project.slug, issue.id)
            if not self._store.is_known(*key):
                verdict, reason = classify_issue(issue, self._store)
                alerts.append(
                    NewIssueAlert(issue=issue, verdict=verdict, verdict_reason=reason)
                )
            self._store.mark_seen(*key)

        for group in groups:
            classify_group(group, self._store)

        if alerts:
            self._notifier.notify_new_issues(alerts)
        self._notifier.notify_digest(groups)
        log.info("poll_done", issues=len(issues), groups=len(groups), new_alerts=len(alerts))
