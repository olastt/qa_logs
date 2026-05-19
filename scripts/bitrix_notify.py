#!/usr/bin/env python3
"""Bitrix24: текст + ссылка на HTML-отчёт на Surge."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def _credentials() -> tuple[str, str]:
    webhook = os.environ.get("BITRIX_WEBHOOK_URL", "").rstrip("/")
    chat_id = os.environ.get("BITRIX_CHAT_ID", "")
    return webhook, chat_id


def send_message(message: str) -> None:
    webhook, chat_id = _credentials()
    if not webhook or not chat_id:
        print("BITRIX_WEBHOOK_URL или BITRIX_CHAT_ID не заданы — пропуск", file=sys.stderr)
        return
    data = urllib.parse.urlencode({"DIALOG_ID": chat_id, "MESSAGE": message}).encode()
    req = urllib.request.Request(f"{webhook}/im.message.add", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(resp.read().decode())
    except Exception as exc:
        print(f"Bitrix notify failed: {exc}", file=sys.stderr)


def send_report_link(message: str, report_url: str) -> None:
    """Сообщение в чат со ссылкой на HTML на Surge (как в автотестах)."""
    webhook, chat_id = _credentials()
    if not webhook or not chat_id:
        print("BITRIX_WEBHOOK_URL или BITRIX_CHAT_ID не заданы — пропуск", file=sys.stderr)
        return

    url = report_url.strip()
    if not url.startswith("http"):
        url = f"https://{url.lstrip('/')}"

    attach = json.dumps(
        [{"LINK": {"NAME": "📊 HTML-отчёт QA", "LINK": url}}],
        ensure_ascii=False,
    )
    full_message = f"{message}\n\n📊 Отчёт: {url}"
    data = urllib.parse.urlencode(
        {
            "DIALOG_ID": chat_id,
            "MESSAGE": full_message,
            "ATTACH": attach,
        }
    ).encode()
    req = urllib.request.Request(f"{webhook}/im.message.add", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(resp.read().decode())
    except Exception as exc:
        print(f"Bitrix notify failed: {exc}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: bitrix_notify.py <message> | bitrix_notify.py --url <message> <report_url>",
            file=sys.stderr,
        )
        sys.exit(1)

    if sys.argv[1] == "--url":
        if len(sys.argv) < 4:
            print("Usage: bitrix_notify.py --url <message> <report_url>", file=sys.stderr)
            sys.exit(1)
        send_report_link(sys.argv[2], sys.argv[3])
        return

    send_message(sys.argv[1])


if __name__ == "__main__":
    main()
