from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class StackFrame:
    filename: str = ""
    function: str = ""
    line_no: int | None = None
    in_app: bool = False

    def display(self) -> str:
        loc = self.filename or "?"
        fn = self.function or "?"
        line = f":{self.line_no}" if self.line_no else ""
        return f"{fn} ({loc}{line})"


@dataclass(slots=True)
class IssueRecord:
    id: str
    title: str
    level: str
    count: int
    last_seen: datetime
    first_seen: datetime
    culprit: str
    org_slug: str = ""
    project_slug: str = ""
    project_id: str = ""
    stack_frames: list[StackFrame] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "count": self.count,
            "level": self.level,
            "last_seen": _iso(self.last_seen),
            "first_seen": _iso(self.first_seen),
            "culprit": self.culprit,
            "org_slug": self.org_slug,
            "project_slug": self.project_slug,
            "project_id": self.project_id,
            "stack_frames": [asdict(f) for f in self.stack_frames[:5]],
        }

    @classmethod
    def from_snapshot_dict(cls, raw: dict[str, Any]) -> IssueRecord:
        return cls(
            id=str(raw["id"]),
            title=raw.get("title") or "",
            level=raw.get("level") or "error",
            count=int(raw.get("count") or 0),
            last_seen=_parse_iso(raw.get("last_seen")),
            first_seen=_parse_iso(raw.get("first_seen")),
            culprit=raw.get("culprit") or "",
            org_slug=str(raw.get("org_slug") or ""),
            project_slug=str(raw.get("project_slug") or ""),
            project_id=str(raw.get("project_id") or ""),
            stack_frames=[
                StackFrame(
                    filename=f.get("filename") or "",
                    function=f.get("function") or "",
                    line_no=f.get("line_no"),
                    in_app=bool(f.get("in_app")),
                )
                for f in (raw.get("stack_frames") or [])[:5]
            ],
        )


def _iso(dt: datetime) -> str:
    if dt.tzinfo:
        return dt.astimezone().isoformat().replace("+00:00", "Z")
    return dt.isoformat() + "Z"


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
