from datetime import datetime, timezone

from qa_release_bot.analyzer import Severity, analyze_issue
from qa_release_bot.models import NormalizedIssue
from qa_release_bot.taxonomy import IssueCategory


def test_medicalcard_null_blocker_on_stage():
    issue = NormalizedIssue(
        id="1",
        short_id="1",
        title="TypeError: Cannot assign null to property Entity\\MedicalCard\\Diagnoses::$medicalCardId",
        level="error",
        count=7,
        last_seen=datetime.now(timezone.utc),
        stack_trace=None,
        environment="stage",
        project_slug="app-stage",
        instance="hetzner",
    )
    result = analyze_issue(issue, only_in_stage=True)
    assert result.category == IssueCategory.PRODUCT
    assert result.severity == Severity.BLOCKER
    assert result.user_impact == 5
    assert result.regression is True


def test_high_count_test_cdb_not_auto_blocker():
    issue = NormalizedIssue(
        id="2",
        short_id="2",
        title="CDbException: Невозможно удалить запись active record из-за того, что она новая.",
        level="error",
        count=559,
        last_seen=datetime.now(timezone.utc),
        stack_trace=None,
        environment="test",
        project_slug="app-test",
        instance="hetzner",
    )
    result = analyze_issue(issue, only_in_stage=False)
    assert result.category == IssueCategory.PRODUCT
    assert result.severity != Severity.BLOCKER or result.user_impact < 5
