from datetime import datetime, timezone

from qa_release_bot.compare import compare_environments
from qa_release_bot.models import NormalizedIssue


def _norm(issue_id: str, title: str, env: str) -> NormalizedIssue:
    now = datetime.now(timezone.utc)
    return NormalizedIssue(
        id=issue_id,
        short_id=issue_id,
        title=title,
        level="error",
        count=1,
        last_seen=now,
        stack_trace=None,
        environment=env,
        project_slug="p",
        instance="hetzner",
    )


def test_compare_only_test_and_only_stage():
    test = [_norm("1", "Error A", "test"), _norm("2", "Error B", "test")]
    stage = [_norm("3", "Error A", "stage"), _norm("4", "Error C", "stage")]

    result = compare_environments(
        test,
        stage,
        product_name="demo",
        test_project="demo-test",
        stage_project="demo-stage",
    )

    assert result.test_count == 2
    assert result.stage_count == 2
    assert len(result.only_test) == 1
    assert result.only_test[0].title == "Error B"
    assert len(result.only_stage) == 1
    assert result.only_stage[0].title == "Error C"
    assert len(result.in_both) == 1
