# Запуск GitHub Actions из Bitrix24

Сейчас цепочка **GitHub → Bitrix** (отчёт в чат). Обратно **Bitrix → GitHub** делается через API `workflow_dispatch`.

## Что понадобится

1. **GitHub Personal Access Token** (classic) или fine-grained:
   - права: `repo` + **Actions: Read and write**
   - сохранить в надёжном месте (не в репозитории)

2. Репозиторий: `olastt/qa_logs`, workflow: `qa-logs.yml`, ветка: `main`

## Способ 1 — без своего сервера (робот Bitrix + HTTP-запрос)

В Bitrix24: **Автоматизация** / **Роботы** / **Исходящий вебхук** → действие **HTTP-запрос**.

| Поле | Значение |
|------|----------|
| URL | `https://api.github.com/repos/olastt/qa_logs/actions/workflows/qa-logs.yml/dispatches` |
| Метод | POST |
| Заголовок | `Authorization: Bearer <GITHUB_TOKEN>` |
| Заголовок | `Accept: application/vnd.github+json` |
| Заголовок | `Content-Type: application/json` |
| Тело | см. ниже |

```json
{
  "ref": "main",
  "inputs": {
    "action": "📊 Сводка — что нового",
    "project": "webapps-widgets",
    "notify_bitrix": true
  }
}
```

Для релиза замените `action` на:

```json
"action": "🚦 Проверить релиз"
```

`project` — id из `qa-bot projects` или `ВСЕ ПРОЕКТЫ`.

Триггеры в Bitrix: кнопка в чате, команда бота, сделка в CRM — как настроите в автоматизации.

## Способ 2 — команды в чате (мини-сервер в репозитории)

Удобно, если в чат пишут текстом: `summary webapps-widgets`.

```bash
set GITHUB_TOKEN=ghp_...
set BITRIX_TRIGGER_SECRET=длинная-случайная-строка
python scripts/bitrix_webhook_server.py --port 8787
```

Сервер должен быть доступен из интернета (HTTPS через nginx / Cloudflare Tunnel).

**POST** `https://ваш-хост/trigger`

```json
{
  "secret": "длинная-случайная-строка",
  "text": "summary webapps-widgets"
}
```

Или:

```json
{
  "secret": "...",
  "action": "summary",
  "project": "hetzner-vetmanager-extjs-stage",
  "notify_bitrix": true
}
```

В Bitrix исходящий вебхук на сообщение в чате передаёт `text` из текста сообщения (настройте шаблон в роботе).

### Примеры команд

| Текст в чате | Действие |
|--------------|----------|
| `/qa summary webapps-widgets` | Сводка widgets (Selectel test) |
| `/qa release vetmanager-extjs` | Релиз extjs test↔stage |
| `сводка hetzner-vetmanager-extjs-stage` | Сводка stage |
| `summary all` | Все проекты сводки |

## Способ 3 — с вашего ПК / CI

```bash
set GITHUB_TOKEN=ghp_...
python scripts/github_dispatch.py summary webapps-widgets
python scripts/github_dispatch.py --release vetmanager-extjs
```

## Проверка

После запуска откройте:

https://github.com/olastt/qa_logs/actions

Должен появиться новый run **QA Logs (Glitchtip)**.

## Безопасность

- Токен GitHub — только на сервере / в секретах Bitrix, не в коде.
- Для способа 2 обязателен `BITRIX_TRIGGER_SECRET`.
- Токен с минимальными правами только на репозиторий `qa_logs`.
