from __future__ import annotations

from collections import defaultdict

from qa_release_bot.models import GlitchtipIssue, IssueGroup, NormalizedIssue, TitleGroup


def group_issues(issues: list[GlitchtipIssue]) -> list[IssueGroup]:
    """
    Группирует issues по fingerprint (тип + сообщение + файл + функция).

    Позже можно усилить: stack trace hash, нормализация сообщений, ML-кластеризация.
    """
    buckets: dict[str, list[GlitchtipIssue]] = defaultdict(list)
    for issue in issues:
        buckets[issue.fingerprint].append(issue)

    return [
        IssueGroup(
            fingerprint=fp,
            issues=sorted(group, key=lambda i: i.last_seen, reverse=True),
        )
        for fp, group in buckets.items()
    ]


def group_by_title(issues: list[NormalizedIssue]) -> list[TitleGroup]:
    """Группирует нормализованные ошибки по title (дубликаты в одной группе)."""
    buckets: dict[str, list[NormalizedIssue]] = defaultdict(list)
    for issue in issues:
        buckets[issue.title].append(issue)

    groups: list[TitleGroup] = []
    for title, members in buckets.items():
        sorted_members = sorted(members, key=lambda i: i.last_seen, reverse=True)
        groups.append(
            TitleGroup(
                title=title,
                issues=sorted_members,
            )
        )
    return sorted(groups, key=lambda g: g.total_count, reverse=True)


def dedupe_by_title(issues: list[NormalizedIssue]) -> list[NormalizedIssue]:
    """Один issue на title — для подсчёта уникальных ошибок в окружении."""
    groups = group_by_title(issues)
    return [g.representative for g in groups]
