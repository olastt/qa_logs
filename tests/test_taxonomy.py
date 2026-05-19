from datetime import datetime, timezone

from qa_release_bot.analyzer import Severity, analyze_issue
from qa_release_bot.models import NormalizedIssue
from qa_release_bot.taxonomy import IssueCategory, RootCauseCluster, classify_taxonomy


def _issue(title: str, **kwargs) -> NormalizedIssue:
    now = datetime.now(timezone.utc)
    return NormalizedIssue(
        id="1",
        short_id="1",
        title=title,
        level=kwargs.get("level", "error"),
        count=kwargs.get("count", 10),
        last_seen=now,
        stack_trace=kwargs.get("stack_trace"),
        environment=kwargs.get("environment", "stage"),
        project_slug="vetmanager-extjs-stage",
        instance="hetzner",
        metadata=kwargs.get("metadata", {}),
    )


def test_rabbitmq_is_infrastructure_not_blocker():
    issue = _issue(
        "Vetmanager\\Workers\\Exception\\RabbitMQCantConnectException: Can`t connect to RabbitMQ",
        count=79,
    )
    tax = classify_taxonomy(issue, only_in_stage=True)
    analysis = analyze_issue(issue, only_in_stage=True)
    assert tax.category == IssueCategory.INFRASTRUCTURE
    assert analysis.severity == Severity.LOW
    assert analysis.regression is False
    assert analysis.user_impact <= 2


def test_file_put_contents_is_noise():
    issue = _issue(
        "ErrorException: Warning: file_put_contents(/var/www/vetmanager/build/tasks/123): Permission denied",
        level="warning",
        count=1,
    )
    tax = classify_taxonomy(issue, only_in_stage=False)
    assert tax.category == IssueCategory.NOISE
    assert tax.user_impact <= 1


def test_medicalcard_null_is_product_blocker():
    issue = _issue(
        "TypeError: Cannot assign null to property Entity\\MedicalCard\\Diagnoses::$medicalCardId of type int",
        metadata={"type": "TypeError", "function": "save", "filename": "Diagnoses.php"},
    )
    tax = classify_taxonomy(issue, only_in_stage=True)
    analysis = analyze_issue(issue, only_in_stage=True)
    assert tax.category == IssueCategory.PRODUCT
    assert tax.cluster == RootCauseCluster.NULL_HANDLING
    assert tax.user_impact == 5
    assert analysis.severity == Severity.BLOCKER
    assert analysis.regression is True


def test_fk_integrity_is_product():
    issue = _issue(
        "CDbException: CDbCommand SQLSTATE[23000]: Integrity constraint violation: 1451 Cannot delete parent row",
    )
    tax = classify_taxonomy(issue, only_in_stage=False)
    assert tax.category == IssueCategory.PRODUCT
    assert tax.cluster == RootCauseCluster.DB_INTEGRITY
