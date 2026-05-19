# QA Release Bot

Мониторинг Glitchtip: сбор ошибок, группировка, классификация для релиза, алерты по новым issue.

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
# заполните GLITCHTIP_*_TOKEN в .env

qa-bot projects                    # все проекты (16 сводок + 1 релиз)
qa-bot release vetmanager-extjs    # проверка релиза (test + stage)
qa-bot summary webapps-widgets     # сводка Selectel widgets-test (алиас)
qa-bot summary hetzner-vetmanager-extjs-stage
qa-bot summary selectel-vetmanager-extjs-production
qa-bot release vetmanager-extjs --no-stack --notify

# алиас: qa-release-bot = qa-bot
```

Токены только в `.env`, не в репозитории.

При вставке в GitHub Secrets **без пробела в конце** — иначе была ошибка `Illegal header value`.

## GitHub Actions

Вкладка **Actions → QA Logs (Glitchtip) → Run workflow**:

| Поле | Значение |
|------|----------|
| Что запустить | 🚦 Проверить релиз / 📊 Сводка |
| Проект | extjs / widgets / laravel / все сразу |
| Bitrix24 | да / нет |

По расписанию (пн–пт 10:00 МСК) — `release vetmanager-extjs`.

Отчёты публикуются на Surge: `qa-extjs-release.surge.sh`, `qa-widgets-summary.surge.sh` и т.д.

### Secrets (Settings → Secrets and variables → Actions)

| Secret | Назначение |
|--------|------------|
| `GLITCHTIP_HETZNER_URL` | URL Hetzner Glitchtip |
| `GLITCHTIP_HETZNER_TOKEN` | API token |
| `GLITCHTIP_SELECTEL_URL` | URL Selectel Glitchtip |
| `GLITCHTIP_SELECTEL_TOKEN` | API token |
| `GLITCHTIP_ORG_SLUG` | `vetmanager` (если Secret пустой — подставится автоматически) |
| `BITRIX_WEBHOOK_URL` | Webhook Bitrix24 (без `/im.message.add`) |
| `BITRIX_CHAT_ID` | ID чата |
| `SURGE_TOKEN` | Токен [surge.sh](https://surge.sh) |
| `SURGE_REPORT_DOMAIN` | Домен для `report`, напр. `qa-extjs.surge.sh` |
| `SURGE_SUMMARY_DOMAIN` | Домен для `summary`, напр. `qa-widgets.surge.sh` |
| `SURGE_QA_LOGS_DOMAIN` | Запасной домен, если не заданы report/summary |

**HTML в чат:** для `report` / `summary` отчёт выкладывается на Surge, в Bitrix приходит ссылка `📊 Отчёт: https://…` (как у автотестов).

Артефакты Actions: `reports/*.html`, markdown и лог run.

## Запуск из Bitrix24 → GitHub

Обратная связь: команда в Bitrix запускает workflow, результат снова приходит в чат.

Подробно: [docs/bitrix-github-trigger.md](docs/bitrix-github-trigger.md)

Кратко:

1. Создайте GitHub PAT с правом **actions:write**.
2. В Bitrix робот **HTTP POST** на  
   `https://api.github.com/repos/olastt/qa_logs/actions/workflows/qa-logs.yml/dispatches`  
   с телом `{"ref":"main","inputs":{"action":"📊 Сводка — что нового","project":"webapps-widgets","notify_bitrix":true}}`.
3. Или поднимите `python scripts/bitrix_webhook_server.py` и шлите команды вида  
   `summary webapps-widgets` из чата.

```bash
python scripts/github_dispatch.py summary webapps-widgets
```
