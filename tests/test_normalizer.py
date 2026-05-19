from datetime import datetime, timezone

from qa_release_bot.models import GlitchtipIssue, GlitchtipProjectRef
from qa_release_bot.normalizer import build_stack_trace_summary, normalize_issue


def _raw_issue() -> GlitchtipIssue:
    project = GlitchtipProjectRef(instance="hetzner", org_slug="vetmanager", slug="app-test")
    now = datetime.now(timezone.utc)
    return GlitchtipIssue(
        id="99",
        short_id="APP-99",
        project=project,
        title="Server  error",
        culprit="main.dart",
        level="error",
        status="unresolved",
        count=42,
        user_count=1,
        first_seen=now,
        last_seen=now,
        metadata={
            "type": "ApiException",
            "value": "Server error",
            "filename": "base.dart",
            "function": "fetchData",
        },
    )


def test_normalize_issue_fields():
    norm = normalize_issue(_raw_issue(), environment="test")
    assert norm.id == "99"
    assert norm.title == "Server error"
    assert norm.level == "error"
    assert norm.count == 42
    assert norm.environment == "test"
    assert norm.stack_trace is not None
    assert "ApiException" in norm.stack_trace
    assert "fetchData" in norm.stack_trace


def test_build_stack_trace_empty():
    assert build_stack_trace_summary({}) is None
