from datetime import datetime, timezone

from qa_release_bot.issue_explain import explain_what_happened
from qa_release_bot.issue_explain_summary import build_summary_what_happened
from qa_release_bot.issue_record import IssueRecord, StackFrame
from qa_release_bot.module_map import ModuleResolution, resolve_module


def test_summary_what_includes_module_and_stack():
    now = datetime.now(timezone.utc)
    issue = IssueRecord(
        id="5536",
        title="TypeError: foo",
        level="error",
        count=3,
        last_seen=now,
        first_seen=now,
        culprit="GET /api/billing",
        stack_frames=[
            StackFrame(
                filename="BillingController.php",
                function="BillingController::index",
                in_app=True,
            )
        ],
        metadata={"type": "TypeError", "value": "null given"},
    )
    resolution = resolve_module(issue, {})
    base, _ = explain_what_happened(issue)
    text = build_summary_what_happened(issue, resolution, base, hypothesis="вероятно null")
    assert "Раздел:" in text or "Компонент:" in text or "Billing" in text
    assert "TypeError" in text or "null" in text
    assert "Место в коде:" in text or "В коде:" in text
