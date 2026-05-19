from __future__ import annotations

from dataclasses import dataclass, field

from qa_release_bot.models import NormalizedIssue


@dataclass(slots=True)
class EnvironmentComparison:
    """Результат сравнения test и stage по title."""

    product_name: str
    test_project: str
    stage_project: str
    test_issues: list[NormalizedIssue] = field(default_factory=list)
    stage_issues: list[NormalizedIssue] = field(default_factory=list)
    only_test: list[NormalizedIssue] = field(default_factory=list)
    only_stage: list[NormalizedIssue] = field(default_factory=list)
    in_both: list[tuple[NormalizedIssue, NormalizedIssue]] = field(default_factory=list)

    @property
    def test_count(self) -> int:
        return len(self.test_issues)

    @property
    def stage_count(self) -> int:
        return len(self.stage_issues)


def compare_environments(
    test_issues: list[NormalizedIssue],
    stage_issues: list[NormalizedIssue],
    *,
    product_name: str,
    test_project: str,
    stage_project: str,
) -> EnvironmentComparison:
    """Сравнивает окружения по нормализованному title."""
    test_by_title = _index_by_title(test_issues)
    stage_by_title = _index_by_title(stage_issues)

    test_titles = set(test_by_title)
    stage_titles = set(stage_by_title)

    only_test_titles = test_titles - stage_titles
    only_stage_titles = stage_titles - test_titles
    both_titles = test_titles & stage_titles

    return EnvironmentComparison(
        product_name=product_name,
        test_project=test_project,
        stage_project=stage_project,
        test_issues=test_issues,
        stage_issues=stage_issues,
        only_test=[test_by_title[t] for t in sorted(only_test_titles)],
        only_stage=[stage_by_title[t] for t in sorted(only_stage_titles)],
        in_both=[
            (test_by_title[t], stage_by_title[t])
            for t in sorted(both_titles, key=lambda x: x.lower())
        ],
    )


def _index_by_title(issues: list[NormalizedIssue]) -> dict[str, NormalizedIssue]:
    """Один представитель на title — с максимальным count, затем last_seen."""
    result: dict[str, NormalizedIssue] = {}
    for issue in issues:
        existing = result.get(issue.title)
        if existing is None or _issue_priority(issue) > _issue_priority(existing):
            result[issue.title] = issue
    return result


def _issue_priority(issue: NormalizedIssue) -> tuple[int, float]:
    ts = issue.last_seen.timestamp() if issue.last_seen.tzinfo else issue.last_seen.timestamp()
    return issue.count, ts
