from __future__ import annotations

import json
import re
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


class GlitchtipApiError(RuntimeError):
    """Ответ Glitchtip не JSON или пустой — неверный URL, org_slug или токен."""


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
        self._base_url = base_url.strip().rstrip("/")
        clean_token = token.strip()
        self._opts = options or ApiClientOptions()
        self._project_id_cache: dict[tuple[str, str], str] = {}
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {clean_token}"},
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

    def _parse_json(self, response: httpx.Response) -> Any:
        url = str(response.request.url)
        body = (response.text or "").strip()
        if not body:
            raise GlitchtipApiError(
                f"Пустой ответ Glitchtip (HTTP {response.status_code}): {url}\n"
                "Проверьте GLITCHTIP_*_URL, GLITCHTIP_ORG_SLUG (vetmanager) и токен."
            )
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            preview = body[:400].replace("\n", " ")
            raise GlitchtipApiError(
                f"Не JSON от Glitchtip (HTTP {response.status_code}): {url}\n"
                f"Начало ответа: {preview!r}\n"
                "Часто: неверный org_slug, токен без прав или URL не API."
            ) from exc

    def list_projects(self) -> list[dict[str, Any]]:
        return self._parse_json(self._get("/api/0/projects/"))

    def list_issues(
        self,
        project: GlitchtipProjectRef,
        *,
        query: str = "is:unresolved",
        stats_period: str = "24h",
        limit: int = 100,
    ) -> list[GlitchtipIssue]:
        path = f"/api/0/projects/{project.org_slug}/{project.slug}/issues/"
        data = self._parse_json(
            self._get(
                path,
                query=query,
                statsPeriod=stats_period,
                limit=limit,
            )
        )
        if not isinstance(data, list):
            raise GlitchtipApiError(
                f"Ожидался список issues, получено {type(data).__name__} "
                f"для {project.org_slug}/{project.slug}"
            )
        return [self._parse_issue(item, project) for item in data]

    def fetch_all_issue_records(
        self,
        project: GlitchtipProjectRef,
        *,
        query: str | None = None,
        stats_period: str = "90d",
        page_limit: int = 100,
        max_issues: int = 2500,
    ) -> list[IssueRecord]:
        """Все issue проекта (с пагинацией) — для «новых за сегодня»."""
        fallback_project_id = self._lookup_project_id(project)
        collected: list[GlitchtipIssue] = []
        cursor: str | None = None
        while len(collected) < max_issues:
            batch, cursor = self._list_issues_page(
                project,
                query=query,
                stats_period=stats_period,
                limit=min(page_limit, max_issues - len(collected)),
                cursor=cursor,
            )
            collected.extend(batch)
            if not batch or not cursor:
                break

        records: list[IssueRecord] = []
        for issue in collected:
            records.append(
                IssueRecord(
                    id=issue.id,
                    title=issue.title,
                    level=issue.level,
                    count=issue.count,
                    last_seen=issue.last_seen,
                    first_seen=issue.first_seen,
                    culprit=issue.culprit,
                    org_slug=project.org_slug,
                    project_slug=project.slug,
                    project_id=issue.project_numeric_id or fallback_project_id,
                    stack_frames=_frames_from_metadata(issue.metadata)[:5],
                    metadata=issue.metadata,
                )
            )
        log.info(
            "issues_loaded_all",
            project=project.slug,
            total=len(records),
            query=query or "(all)",
        )
        return records

    def _list_issues_page(
        self,
        project: GlitchtipProjectRef,
        *,
        query: str | None,
        stats_period: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[GlitchtipIssue], str | None]:
        path = f"/api/0/projects/{project.org_slug}/{project.slug}/issues/"
        params: dict[str, Any] = {
            "statsPeriod": stats_period,
            "limit": limit,
        }
        if query is not None:
            params["query"] = query
        if cursor:
            params["cursor"] = cursor
        response = self._get(path, **params)
        data = self._parse_json(response)
        if not isinstance(data, list):
            raise GlitchtipApiError(
                f"Ожидался список issues, получено {type(data).__name__} "
                f"для {project.org_slug}/{project.slug}"
            )
        issues = [self._parse_issue(item, project) for item in data]
        return issues, _next_cursor_from_link(response.headers.get("Link"))

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

        fallback_project_id = self._lookup_project_id(project)
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
                    org_slug=project.org_slug,
                    project_slug=project.slug,
                    project_id=issue.project_numeric_id or fallback_project_id,
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
            return _extract_frames(self._parse_json(response))
        except GlitchtipApiError:
            return []
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                log.warning("stack_skipped_rate_limit", issue_id=issue_id)
                return []
            return []
        except Exception:
            return []

    def _lookup_project_id(self, project: GlitchtipProjectRef) -> str:
        key = (project.org_slug, project.slug)
        if key in self._project_id_cache:
            return self._project_id_cache[key]
        found = ""
        try:
            for item in self.list_projects():
                if not isinstance(item, dict):
                    continue
                slug = item.get("slug") or ""
                org = ""
                org_raw = item.get("organization")
                if isinstance(org_raw, dict):
                    org = str(org_raw.get("slug") or "")
                if slug == project.slug and (not org or org == project.org_slug):
                    found = str(item.get("id") or "")
                    break
        except Exception:
            log.warning("project_id_lookup_failed", slug=project.slug)
        self._project_id_cache[key] = found
        return found

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
            project_numeric_id=_project_id_from_raw(raw),
            metadata=metadata,
        )


def _next_cursor_from_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for chunk in link_header.split(","):
        if 'rel="next"' not in chunk or 'results="false"' in chunk:
            continue
        match = re.search(r'cursor="([^"]+)"', chunk)
        if match:
            return match.group(1)
    return None


def _project_id_from_raw(raw: dict[str, Any]) -> str:
    proj = raw.get("project")
    if isinstance(proj, dict) and proj.get("id") is not None:
        return str(proj["id"])
    if proj is not None and not isinstance(proj, dict):
        return str(proj)
    return ""


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
