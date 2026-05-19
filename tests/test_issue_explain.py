from datetime import datetime, timezone

from qa_release_bot.issue_analysis import analyze_issue_full
from qa_release_bot.issue_explain import explain_what_happened
from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.severity_rules import IssueSeverity


def _issue(title: str) -> IssueRecord:
    now = datetime.now(timezone.utc)
    return IssueRecord(
        id="99",
        title=title,
        level="error",
        count=5,
        last_seen=now,
        first_seen=now,
        culprit="",
    )


def test_sync_admission_explanation_unique():
    what, clear = explain_what_happened(
        _issue("SyncAdmissionVetmanagerJob: user admission sync failed")
    )
    assert "фонов" in what.lower()
    assert "vetmanager" in what.lower()
    assert clear


def test_google_calendar_explanation_unique():
    what, _ = explain_what_happened(_issue("GoogleCalendarSyncScheduleJob: user sync failed"))
    assert "google calendar" in what.lower()
    assert "расписан" in what.lower()


def test_unclear_title_fallback():
    what, clear = explain_what_happened(_issue("SomeUnknownXYZ: opaque failure"))
    assert what.startswith("Требует уточнения у разработчика:")
    assert not clear


def test_clear_issue_has_hypothesis_not_generic_questions():
    a = analyze_issue_full(
        _issue("SyncAdmissionVetmanagerJob: user admission sync failed"),
        IssueSeverity.HIGH,
    )
    assert not a.dev_questions
    assert a.dev_hypothesis


def test_wazapa_has_specific_question():
    a = analyze_issue_full(_issue("WazapaGetStatus error: {}"), IssueSeverity.MEDIUM)
    assert a.dev_questions
    assert "wazapa" in a.dev_questions[0].lower()
    assert not any("тестовые данные на stage" in q.lower() for q in a.dev_questions)
