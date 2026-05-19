from __future__ import annotations

import structlog

from qa_release_bot.models import IssueGroup, NewIssueAlert, ReleaseVerdict

log = structlog.get_logger(__name__)

_VERDICT_LABEL = {
    ReleaseVerdict.BLOCKER: "БЛОКЕР РЕЛИЗА",
    ReleaseVerdict.DEFER: "можно отложить",
    ReleaseVerdict.REGRESSION: "РЕГРЕССИЯ",
}


class Notifier:
    """Слой оповещений. Сейчас — structured log; далее Telegram/Slack."""

    def notify_new_issues(self, alerts: list[NewIssueAlert]) -> None:
        for alert in alerts:
            issue = alert.issue
            label = _VERDICT_LABEL[alert.verdict]
            log.info(
                "new_issue",
                instance=issue.project.instance,
                project=issue.project.display_name,
                short_id=issue.short_id,
                title=issue.title,
                level=issue.level,
                count=issue.count,
                verdict=label,
                reason=alert.verdict_reason,
            )

    def notify_digest(self, groups: list[IssueGroup]) -> None:
        blockers = [g for g in groups if g.verdict == ReleaseVerdict.BLOCKER]
        regressions = [g for g in groups if g.verdict == ReleaseVerdict.REGRESSION]
        log.info(
            "digest",
            total_groups=len(groups),
            blockers=len(blockers),
            regressions=len(regressions),
        )
