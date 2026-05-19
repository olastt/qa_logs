#!/usr/bin/env python3
"""Отправка сообщения в Bitrix24 (im.message.add) — для GitHub Actions."""

from __future__ import annotations

import os
import sys
import urllib.parse
import urllib.request


def send_message(message: str) -> None:
    webhook = os.environ.get("BITRIX_WEBHOOK_URL", "").rstrip("/")
    chat_id = os.environ.get("BITRIX_CHAT_ID", "")
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


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: bitrix_notify.py <message>", file=sys.stderr)
        sys.exit(1)
    send_message(sys.argv[1])


if __name__ == "__main__":
    main()
