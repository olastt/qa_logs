#!/usr/bin/env python3
"""Bitrix24: текст, ссылка на HTML и вложение .html в чат."""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import httpx


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


def _upload_html_to_disk(webhook: str, html_path: Path) -> str | None:
    """Загрузка HTML в диск Bitrix24, возвращает ID файла для FILES."""
    try:
        with httpx.Client(timeout=120) as client:
            r = client.get(f"{webhook}/disk.storage.getlist")
            r.raise_for_status()
            payload = r.json()
            if payload.get("error"):
                print(f"disk.storage.getlist: {payload}", file=sys.stderr)
                return None
            storages = payload.get("result") or []
            if not storages:
                print("Bitrix: нет хранилищ (у webhook нужен scope disk)", file=sys.stderr)
                return None
            storage = storages[0]
            storage_id = storage["ID"]
            folder_id = storage.get("ROOT_OBJECT_ID") or storage_id

            content_b64 = base64.b64encode(html_path.read_bytes()).decode()
            r = client.post(
                f"{webhook}/disk.storage.uploadfile",
                data={
                    "id": storage_id,
                    "generateUniqueName": "Y",
                    "data[NAME]": html_path.name,
                    "fileContent[0]": content_b64,
                },
            )
            result = r.json()
            if not result.get("error") and (result.get("result") or {}).get("ID"):
                file_id = result["result"]["ID"]
                print(f"Bitrix: файл загружен (storage), ID={file_id}")
                return str(file_id)

            if result.get("error"):
                print(f"disk.storage.uploadfile: {result} — пробуем folder.uploadfile", file=sys.stderr)

            r = client.post(
                f"{webhook}/disk.folder.uploadfile",
                data={
                    "id": folder_id,
                    "generateUniqueName": "Y",
                    "data": json.dumps({"NAME": html_path.name}, ensure_ascii=False),
                },
            )
            r.raise_for_status()
            up = r.json()
            if up.get("error"):
                print(f"disk.folder.uploadfile: {up}", file=sys.stderr)
                return None
            upload_url = (up.get("result") or {}).get("uploadUrl")
            field = (up.get("result") or {}).get("field") or "file"
            if not upload_url:
                return None
            with html_path.open("rb") as fh:
                r2 = client.post(
                    upload_url,
                    files={field: (html_path.name, fh, "text/html")},
                )
            r2.raise_for_status()
            body = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
            file_id = (body.get("result") or {}).get("ID") or (body.get("result") or {}).get("FILE_ID")
            if not file_id and isinstance(body.get("result"), dict):
                file_id = body["result"].get("id")
            if file_id:
                print(f"Bitrix: файл загружен (folder), ID={file_id}")
                return str(file_id)
            print(f"Bitrix: upload OK, но нет ID в ответе: {body}", file=sys.stderr)
            return None
    except Exception as exc:
        print(f"Bitrix upload failed: {exc}", file=sys.stderr)
        return None


def _send_with_files(
    webhook: str,
    chat_id: str,
    message: str,
    file_ids: list[str],
    *,
    report_url: str | None = None,
) -> None:
    attach: list[dict] = []
    if report_url:
        attach.append(
            {
                "LINK": {
                    "NAME": "Открыть HTML-отчёт в браузере",
                    "LINK": report_url,
                }
            }
        )

    data: dict[str, str] = {
        "DIALOG_ID": chat_id,
        "MESSAGE": message,
    }
    for i, fid in enumerate(file_ids):
        data[f"FILES[{i}]"] = fid
    if attach:
        data["ATTACH"] = json.dumps(attach, ensure_ascii=False)

    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{webhook}/im.message.add", data=body)
    with urllib.request.urlopen(req, timeout=60) as resp:
        print(resp.read().decode())


def publish_report(
    message: str,
    *,
    html_path: Path | None = None,
    report_url: str | None = None,
) -> None:
    """
    Публикует отчёт в чат Bitrix24:
    - вложение .html (если есть файл и scope disk);
    - кнопка-ссылка на Surge (если задан report_url).
    """
    webhook, chat_id = _credentials()
    if not webhook or not chat_id:
        print("BITRIX_WEBHOOK_URL или BITRIX_CHAT_ID не заданы — пропуск", file=sys.stderr)
        return

    file_id: str | None = None
    if html_path and html_path.is_file():
        file_id = _upload_html_to_disk(webhook, html_path)

    if file_id:
        extra = ""
        if report_url:
            extra = f"\n\n🌐 Также в браузере: {report_url}"
        _send_with_files(
            webhook,
            chat_id,
            message + extra,
            [file_id],
            report_url=report_url,
        )
        return

    if report_url:
        attach = json.dumps(
            [
                {
                    "LINK": {
                        "NAME": "📊 HTML-отчёт QA",
                        "LINK": report_url,
                    }
                }
            ],
            ensure_ascii=False,
        )
        data = urllib.parse.urlencode(
            {
                "DIALOG_ID": chat_id,
                "MESSAGE": f"{message}\n\n📊 Отчёт: {report_url}",
                "ATTACH": attach,
            }
        ).encode()
        req = urllib.request.Request(f"{webhook}/im.message.add", data=data)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(resp.read().decode())
        except Exception as exc:
            print(f"Bitrix notify failed: {exc}", file=sys.stderr)
        return

    send_message(message)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: bitrix_notify.py <message> | "
            "bitrix_notify.py --publish <message> [--html path] [--url url]",
            file=sys.stderr,
        )
        sys.exit(1)

    if sys.argv[1] == "--publish":
        msg = sys.argv[2] if len(sys.argv) > 2 else ""
        html: Path | None = None
        url: str | None = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--html" and i + 1 < len(args):
                html = Path(args[i + 1])
                i += 2
            elif args[i] == "--url" and i + 1 < len(args):
                url = args[i + 1]
                i += 2
            else:
                i += 1
        publish_report(msg, html_path=html, report_url=url)
        return

    send_message(sys.argv[1])


if __name__ == "__main__":
    main()
