from datetime import datetime, timedelta, timezone

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.noise_groups import group_noise_issues
from qa_release_bot.release_decision import decide_release
from qa_release_bot.severity_rules import IssueSeverity, classify_severity
from qa_release_bot.snapshot_store import SnapshotStore
from qa_release_bot.tuesday_diff import build_stage_diff, is_stale


def _issue(title: str, count: int = 1, **kwargs) -> IssueRecord:
    now = datetime.now(timezone.utc)
    return IssueRecord(
        id=kwargs.get("id", "1"),
        title=title,
        level=kwargs.get("level", "error"),
        count=count,
        last_seen=kwargs.get("last_seen", now),
        first_seen=kwargs.get("first_seen", now - timedelta(days=1)),
        culprit="",
    )


def test_severity_blocker_by_count():
    assert classify_severity(_issue("x", 201)) == IssueSeverity.BLOCKER


def test_severity_high_range():
    assert classify_severity(_issue("x", 80)) == IssueSeverity.HIGH


def test_noise_grouping():
    issues = [
        _issue("ErrorException: file_put_contents(/tmp/a)", 1),
        _issue("ErrorException: file_put_contents(/tmp/b)", 1),
        _issue("Real bug", 5),
    ]
    deduped, noise, _ = group_noise_issues(issues)
    assert len(noise) == 1
    assert noise[0].issue_count == 2
    assert any(i.title == "Real bug" for i in deduped)


def test_snapshot_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path, retention_days=60)
    issues = [_issue("Test error", 10, id="42")]
    store.save("stage", issues)
    loaded = store.load("stage", datetime.now(timezone.utc).date())
    assert loaded is not None
    assert loaded[0].id == "42"
    assert loaded[0].count == 10


def test_diff_new_and_fixed():
    prev = [_issue("Old", 40, id="1")]
    curr = [_issue("New", 10, id="2")]
    rows = build_stage_diff(curr, prev)
    statuses = {r.title[:3]: r.status for r in rows}
    assert any("новый" in s for s in statuses.values())
    assert any("исправлен" in s for s in statuses.values())


def test_stale_excluded_from_release():
    old = datetime.now(timezone.utc) - timedelta(days=40)
    blockers = [_issue("Fatal", 300, level="fatal", last_seen=old)]
    decision = decide_release(blockers, [])
    assert decision.verdict == "ok"


def test_release_forbidden_with_active_blocker():
    blockers = [_issue("Active fatal", 250, level="fatal")]
    decision = decide_release(blockers, [])
    assert decision.verdict == "forbidden"
