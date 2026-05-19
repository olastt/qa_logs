#!/usr/bin/env python3
"""Запуск GitHub Actions workflow_dispatch (из CLI или Bitrix)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_REPO = "olastt/qa_logs"
DEFAULT_WORKFLOW = "qa-logs.yml"
DEFAULT_REF = "main"

ACTION_RELEASE = "🚦 Проверить релиз"
ACTION_SUMMARY = "📊 Сводка — что нового"


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ValueError("Задайте GITHUB_TOKEN (PAT с правом actions:write)")
    return token


def _repo() -> str:
    return os.environ.get("GITHUB_REPO", DEFAULT_REPO).strip()


def parse_command(text: str) -> tuple[str, str, bool]:
    """
    Разбор команды из чата Bitrix.

    Примеры:
      /qa release vetmanager-extjs
      /qa summary webapps-widgets
      сводка selectel-webappswidgets-test
      релиз hetzner-mobilebackend
      summary all
    """
    raw = text.strip()
    raw = re.sub(r"^/qa\s*", "", raw, flags=re.I).strip()
    raw = re.sub(r"^qa-bot\s*", "", raw, flags=re.I).strip()

    parts = raw.split()
    if len(parts) < 2:
        raise ValueError(
            "Формат: <release|summary|релиз|сводка> <проект>\n"
            "Пример: summary webapps-widgets"
        )

    cmd, project = parts[0].lower(), parts[1]
    if project.lower() in ("all", "все", "*"):
        project = "ВСЕ ПРОЕКТЫ"

    if cmd in ("release", "релиз", "rel"):
        return ACTION_RELEASE, project, True
    if cmd in ("summary", "сводка", "sum"):
        return ACTION_SUMMARY, project, True
    raise ValueError(f"Неизвестная команда «{cmd}». Используйте release или summary")


def dispatch_workflow(
    *,
    action: str,
    project: str,
    notify_bitrix: bool = True,
    repo: str | None = None,
    workflow: str = DEFAULT_WORKFLOW,
    ref: str = DEFAULT_REF,
    token: str | None = None,
) -> dict:
    """POST workflow_dispatch → GitHub API."""
    token = token or _token()
    repo = repo or _repo()
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/actions/workflows/{workflow}/dispatches"

    body = json.dumps(
        {
            "ref": ref,
            "inputs": {
                "action": action,
                "project": project,
                "notify_bitrix": notify_bitrix,
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "repo": repo, "workflow": workflow, "ref": ref}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Запуск QA Logs workflow в GitHub Actions")
    parser.add_argument(
        "command",
        nargs="?",
        help='Команда целиком, напр. "summary webapps-widgets"',
    )
    parser.add_argument("--release", metavar="PROJECT", help="Проверить релиз")
    parser.add_argument("--summary", metavar="PROJECT", help="Сводка")
    parser.add_argument("--no-notify", action="store_true", help="Не слать Bitrix после run")
    parser.add_argument("--repo", default=None, help=f"owner/repo (default {_repo()})")
    args = parser.parse_args()

    notify = not args.no_notify

    if args.release:
        action, project = ACTION_RELEASE, args.release
    elif args.summary:
        action, project = ACTION_SUMMARY, args.summary
    elif args.command:
        action, project, _ = parse_command(args.command)
    else:
        parser.print_help()
        sys.exit(1)

    if project.lower() in ("all", "все"):
        project = "ВСЕ ПРОЕКТЫ"

    result = dispatch_workflow(
        action=action,
        project=project,
        notify_bitrix=notify,
        repo=args.repo,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Запущено: {action} → {project}")
    print(f"https://github.com/{args.repo or _repo()}/actions")


if __name__ == "__main__":
    main()
