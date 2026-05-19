from datetime import datetime, timezone

from qa_release_bot.issue_analysis import analyze_issue_full
from qa_release_bot.issue_record import IssueRecord, StackFrame
from qa_release_bot.module_map import resolve_module
from qa_release_bot.severity_rules import IssueSeverity


def test_tracker_title_not_technical():
    issue = IssueRecord(
        id="1",
        title="CDbException: CDbCommand не удалось исполнить SQL-запрос",
        level="error",
        count=80,
        last_seen=datetime.now(timezone.utc),
        first_seen=datetime.now(timezone.utc),
        culprit="",
        stack_frames=[StackFrame(filename="InvoiceDocumentController.php", function="InvoiceDocumentController::save")],
    )
    a = analyze_issue_full(issue, IssueSeverity.HIGH)
    assert a.tracker_title.startswith("[")
    assert "CDbException" not in a.tracker_title
    assert "ЧТО СЛУЧИЛОСЬ" not in a.what_happened.lower() or "exception" not in a.what_happened.lower()


def test_module_map_controller():
    issue = IssueRecord(
        id="2",
        title="Error in save",
        level="error",
        count=5,
        last_seen=datetime.now(timezone.utc),
        first_seen=datetime.now(timezone.utc),
        culprit="",
        stack_frames=[StackFrame(function="MedicalCardsController::actionView")],
    )
    mod = resolve_module(issue)
    assert mod.human_module is not None
    assert "Медицинские" in mod.human_module or "карт" in mod.human_module.lower()
