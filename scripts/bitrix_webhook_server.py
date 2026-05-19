#!/usr/bin/env python3
"""
Мини-сервер: Bitrix24 → GitHub Actions.

Bitrix «Исходящий вебхук» или робот с HTTP-запросом шлёт POST сюда,
сервер вызывает workflow_dispatch.

Запуск:
  set GITHUB_TOKEN=ghp_...
  set BITRIX_TRIGGER_SECRET=случайная-строка
  python scripts/bitrix_webhook_server.py --port 8787

POST /trigger  (JSON)
  {"secret": "...", "text": "summary webapps-widgets"}
  или {"secret": "...", "action": "summary", "project": "webapps-widgets"}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from github_dispatch import ACTION_RELEASE, ACTION_SUMMARY, dispatch_workflow, parse_command


def _check_secret(got: str) -> None:
    expected = os.environ.get("BITRIX_TRIGGER_SECRET", "").strip()
    if not expected:
        raise ValueError("BITRIX_TRIGGER_SECRET не задан на сервере")
    if got != expected:
        raise PermissionError("Неверный secret")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._json(200, {"ok": True, "service": "qa-bot-bitrix-trigger"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path not in ("/trigger", "/"):
            self._json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")

        data: dict = {}
        if raw.strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {k: v[0] for k, v in parse_qs(raw).items()}

        # Bitrix outgoing webhook: data[MESSAGE], auth[application_token], etc.
        if "data[MESSAGE]" in data or "data[message]" in data:
            text = data.get("data[MESSAGE]") or data.get("data[message]", "")
            secret = data.get("secret") or data.get("auth[application_token]", "")
        else:
            text = str(data.get("text", "") or data.get("message", ""))
            secret = str(data.get("secret", ""))

        try:
            _check_secret(str(secret))

            if data.get("action") and data.get("project"):
                act = str(data["action"]).lower()
                project = str(data["project"])
                if act in ("release", "релиз"):
                    action, notify = ACTION_RELEASE, True
                elif act in ("summary", "сводка"):
                    action, notify = ACTION_SUMMARY, True
                else:
                    raise ValueError("action: release | summary")
                notify_bitrix = str(data.get("notify_bitrix", "true")).lower() != "false"
            else:
                action, project, notify_bitrix = parse_command(text)

            if project.lower() in ("all", "все"):
                project = "ВСЕ ПРОЕКТЫ"

            result = dispatch_workflow(
                action=action,
                project=project,
                notify_bitrix=notify_bitrix,
            )
            self._json(
                200,
                {
                    "ok": True,
                    "message": f"Запущено: {action} → {project}",
                    "github": result,
                },
            )
        except PermissionError as exc:
            self._json(403, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    if not os.environ.get("GITHUB_TOKEN"):
        print("Нужен GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("BITRIX_TRIGGER_SECRET"):
        print("Нужен BITRIX_TRIGGER_SECRET", file=sys.stderr)
        sys.exit(1)

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Listening http://{args.host}:{args.port}/trigger")
    server.serve_forever()


if __name__ == "__main__":
    main()
