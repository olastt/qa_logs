# QA Release Bot

Мониторинг Glitchtip: сбор ошибок, группировка, классификация для релиза, алерты по новым issue.

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
# заполните GLITCHTIP_*_TOKEN в .env

qa-release-bot report              # markdown + HTML reports/qa_report_YYYY-MM-DD.html
qa-release-bot report -o reports/qa.md
qa-release-bot report --pdf        # дополнительно PDF
qa-release-bot report --legacy     # старый текст + PDF test vs stage
qa-release-bot summary             # сводка + HTML (config/report.yaml → summaries)
qa-release-bot summary --instance selectel --project webappswidgets-test
qa-release-bot summary --pdf       # дополнительно PDF
qa-release-bot list-projects
qa-release-bot run-once
qa-release-bot poll
```

Токены только в `.env`, не в репозитории.

## GitHub Actions

Вкладка **Actions → QA Logs (Glitchtip) → Run workflow** — ручной запуск с выбором команды.

| Input | Описание |
|--------|----------|
| `report` | QA-отчёт vetmanager-extjs test + stage |
| `summary` | Сводка по одному проекту (Selectel widgets) |
| `run-once` | Один цикл опроса |
| `list-projects` | Список проектов из config |

По расписанию (пн–пт 10:00 МСК) автоматически запускается `report`.

### Secrets (Settings → Secrets and variables → Actions)

| Secret | Назначение |
|--------|------------|
| `GLITCHTIP_HETZNER_URL` | URL Hetzner Glitchtip |
| `GLITCHTIP_HETZNER_TOKEN` | API token |
| `GLITCHTIP_SELECTEL_URL` | URL Selectel Glitchtip |
| `GLITCHTIP_SELECTEL_TOKEN` | API token |
| `GLITCHTIP_ORG_SLUG` | `vetmanager` |
| `BITRIX_WEBHOOK_URL` | Webhook Bitrix24 (без `/im.message.add`) |
| `BITRIX_CHAT_ID` | ID чата |
| `SURGE_TOKEN` | Токен [surge.sh](https://surge.sh) |
| `SURGE_REPORT_DOMAIN` | Домен для `report`, напр. `qa-extjs.surge.sh` |
| `SURGE_SUMMARY_DOMAIN` | Домен для `summary`, напр. `qa-widgets.surge.sh` |
| `SURGE_QA_LOGS_DOMAIN` | Запасной домен, если не заданы report/summary |

**HTML в чат:** для `report` / `summary` отчёт выкладывается на Surge, в Bitrix приходит ссылка `📊 Отчёт: https://…` (как у автотестов).

Артефакты Actions: `reports/*.html`, markdown и лог run.
