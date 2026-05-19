from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import structlog

from qa_release_bot.api_http import request_with_retry
from qa_release_bot.issue_record import IssueRecord, StackFrame
from qa_release_bot.models import GlitchtipIssue, GlitchtipProjectRef

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ApiClientOptions:
    max_retries: int = 6
    retry_base_sec: float = 2.0
    delay_between_requests_sec: float = 0.0
    enrich_stack: bool = True
    enrich_stack_max_issues: int = 30
    enrich_stack_delay_sec: float = 0.2


class GlitchtipClient:
    """HTTP-клиент к Sentry-совместимому API Glitchtip."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 60.0,
        options: ApiClientOptions | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._opts = options or ApiClientOptions()
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GlitchtipClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get(self, path: str, **params: Any) -> httpx.Response:
        if self._opts.delay_between_requests_sec > 0:
            time.sleep(self._opts.delay_between_requests_sec)
        response = request_with_retry(
            self._client,
            "GET",
            path,
            max_retries=self._opts.max_retries,
            retry_base_sec=self._opts.retry_base_sec,
            params=params or None,
        )
        response.raise_for_status()
        return response

    def list_projects(self) -> list[dict[str, Any]]:
        return self._get("/api/0/projects/").json()

    def list_issues(
        self,
        project: GlitchtipProjectRef,
        *,
        query: str = "is:unresolved",
        stats_period: str = "24h",
        limit: int = 100,
    ) -> list[GlitchtipIssue]:
        path = f"/api/0/projects/{project.org_slug}/{project.slug}/issues/"
        data = self._get(
            path,
            query=query,
            statsPeriod=stats_period,
            limit=limit,
        ).json()
        return [self._parse_issue(item, project) for item in data]

    def fetch_issue_records(
        self,
        project: GlitchtipProjectRef,
        *,
        query: str = "is:unresolved",
        stats_period: str = "14d",
        limit: int = 100,
        enrich_stack: bool | None = None,
    ) -> list[IssueRecord]:
        do_enrich = self._opts.enrich_stack if enrich_stack is None else enrich_stack
        issues = self.list_issues(
            project, query=query, stats_period=stats_period, limit=limit
        )
        issues_sorted = sorted(issues, key=lambda i: -i.count)
        enrich_ids = {
            i.id for i in issues_sorted[: self._opts.enrich_stack_max_issues]
        }

        records: list[IssueRecord] = []
        enriched = 0
        for issue in issues:
            frames: list[StackFrame] = []
            if do_enrich and issue.id in enrich_ids:
                frames = self._fetch_stack_frames(issue.id)
                enriched += 1
            if not frames:
                frames = _frames_from_metadata(issue.metadata)
            records.append(
                IssueRecord(
                    id=issue.id,
                    title=issue.title,
                    level=issue.level,
                    count=issue.count,
                    last_seen=issue.last_seen,
                    first_seen=issue.first_seen,
                    culprit=issue.culprit,
                    stack_frames=frames[:5],
                    metadata=issue.metadata,
                )
            )
        log.info(
            "issues_loaded",
            project=project.slug,
            total=len(records),
            stack_enriched=enriched,
        )
        return records

    def _fetch_stack_frames(self, issue_id: str) -> list[StackFrame]:
        if self._opts.enrich_stack_delay_sec > 0:
            time.sleep(self._opts.enrich_stack_delay_sec)
        try:
            response = request_with_retry(
                self._client,
                "GET",
                f"/api/0/issues/{issue_id}/events/latest/",
                max_retries=self._opts.max_retries,
                retry_base_sec=self._opts.retry_base_sec,
            )
            if response.status_code == 404:
                return []
            if response.status_code == 429:
                return _frames_from_metadata({})
            response.raise_for_status()
            return _extract_frames(response.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                log.warning("stack_skipped_rate_limit", issue_id=issue_id)
                return []
            return []
        except Exception:
            return []

    @staticmethod
    def _parse_issue(raw: dict[str, Any], project: GlitchtipProjectRef) -> GlitchtipIssue:
        metadata = raw.get("metadata") or {}
        return GlitchtipIssue(
            id=str(raw["id"]),
            short_id=raw.get("shortId") or raw["id"],
            project=project,
            title=raw.get("title") or metadata.get("value") or "(no title)",
            culprit=raw.get("culprit") or "",
            level=raw.get("level") or "error",
            status=raw.get("status") or "unresolved",
            count=int(raw.get("count") or 0),
            user_count=int(raw.get("userCount") or 0),
            first_seen=_parse_dt(raw.get("firstSeen")),
            last_seen=_parse_dt(raw.get("lastSeen")),
            metadata=metadata,
        )


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=None)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _frames_from_metadata(metadata: dict[str, Any]) -> list[StackFrame]:
    if not metadata:
        return []
    return [
        StackFrame(
            filename=str(metadata.get("filename") or ""),
            function=str(metadata.get("function") or ""),
        )
    ]


def _extract_frames(event: dict[str, Any]) -> list[StackFrame]:
    frames: list[StackFrame] = []
    entries = event.get("entries") or []
    for entry in entries:
        if entry.get("type") != "exception":
            continue
        for exc in entry.get("data", {}).get("values", []):
            stack = exc.get("stacktrace") or {}
            for raw in stack.get("frames") or []:
                frames.append(
                    StackFrame(
                        filename=str(raw.get("filename") or raw.get("absPath") or ""),
                        function=str(raw.get("function") or ""),
                        line_no=raw.get("lineNo") or raw.get("lineno"),
                        in_app=bool(raw.get("inApp") or raw.get("in_app")),
                    )
                )
    if frames:
        return list(reversed(frames[-5:]))
    for exc in event.get("exception", {}).get("values", []) or []:
        stack = exc.get("stacktrace") or {}
        for raw in stack.get("frames") or []:
            frames.append(
                StackFrame(
                    filename=str(raw.get("filename") or ""),
                    function=str(raw.get("function") or ""),
                    line_no=raw.get("lineno"),
                    in_app=bool(raw.get("in_app")),
                )
            )
    return list(reversed(frames[-5:]))
