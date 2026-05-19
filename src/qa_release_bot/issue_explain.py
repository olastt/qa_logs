"""Уникальные объяснения и вопросы по title issue."""

from __future__ import annotations

import re

from qa_release_bot.issue_record import IssueRecord

_UNCLEAR_PREFIX = "Требует уточнения у разработчика:"


def explain_what_happened(issue: IssueRecord) -> tuple[str, bool]:
    """
    Возвращает (текст «что случилось», понятно_ли_из_title).
    Если непонятно — текст начинается с «Требует уточнения…».
    """
    raw = issue.title.strip()
    t = raw.lower()
    compact = re.sub(r"\s+", "", t)

    if "syncadmissionvetmanagerjob" in compact or (
        "sync" in t and "admission" in t and "vetmanager" in t and "fail" in t
    ):
        return (
            "Фоновая задача не смогла синхронизировать данные приёма с Vetmanager — "
            "запись могла не попасть в основную систему.",
            True,
        )
    if "googlecalendarsyncschedulejob" in compact or (
        "google" in t and "calendar" in t and "sync" in t and "fail" in t
    ):
        return (
            "Расписание пользователя не удалось синхронизировать с Google Calendar — "
            "пациент может не увидеть запись.",
            True,
        )
    if "wrong dev auth key" in t or "dev auth key" in t:
        return (
            "Система не прошла авторизацию с неверным ключом — "
            "вероятно проблема с конфигурацией на окружении.",
            True,
        )
    if "wazapagetstatus" in compact or "wazapa" in t:
        if "{}" in raw or "пуст" in t or "empty" in t:
            return (
                "Не удалось получить статус из Wazapa (WhatsApp-интеграция) — "
                "пустой ответ вместо данных.",
                False,
            )
        return (
            "Сбой при запросе статуса в Wazapa (WhatsApp-интеграция).",
            False,
        )
    if "server error" in t and "billing" in t:
        return (
            "HTTP-запрос к billing API завершился ошибкой — "
            "оплата или тарификация могли не обработаться.",
            True,
        )
    if "cannot assign null" in t and "medicalcard" in t:
        return (
            "При сохранении медкарты в обязательное поле попало пустое значение — "
            "запись не сохраняется.",
            True,
        )
    if "cannot assign null" in t:
        return (
            "В обязательное поле попало пустое (null) значение — операция не завершается.",
            True,
        )
    if "active record" in t and "новая" in t:
        return (
            "Попытка изменить или удалить запись, которая ещё не была сохранена в базе.",
            True,
        )
    if "integrity constraint" in t or "1451" in t:
        return (
            "Нарушение связей в БД — нельзя удалить или изменить запись из‑за зависимостей.",
            True,
        )
    if "hasattribute" in t and "null" in t:
        return (
            "Объект не загрузился (null) — форма могла отправиться до готовности данных.",
            True,
        )
    if "undefined array key" in t:
        return (
            "В запросе или форме отсутствует ожидаемое поле — данные пришли неполными.",
            True,
        )
    if "rabbitmq" in t:
        return (
            "Фоновая очередь RabbitMQ недоступна — отложенные задачи не выполняются.",
            True,
        )
    if "clickhouse" in t:
        return (
            "Не удаётся записать данные в ClickHouse (аналитика) — на интерфейс обычно не влияет.",
            True,
        )
    if "file_put_contents" in t:
        return (
            "Сервер не смог записать файл (права доступа или диск).",
            True,
        )
    if "jsonapiwithcodeexception" in compact or (
        "jsonapi" in t and "exception" in t
    ):
        hint = _after_colon(raw)
        if hint:
            return (f"API вернул ошибку: {hint[:200]}.", True)
    if "prescription" in t and ("send" in t or "отправ" in t):
        return ("Не удалось отправить рецепт — пациент или врач могут не получить документ.", True)
    if "timeout" in t or "timed out" in t:
        where = _job_or_service_name(raw)
        return (
            f"Превышено время ожидания{where} — внешний сервис или БД не ответили вовремя.",
            True,
        )
    if "connection refused" in t or "could not connect" in t:
        return (
            "Нет соединения с внешним сервисом или БД — хост недоступен или неверный адрес.",
            True,
        )
    if issue.level == "fatal" and _looks_technical(raw):
        return (f"{_UNCLEAR_PREFIX} {raw}", False)

    if _looks_technical(raw) and not _has_cyrillic_hint(raw):
        return (f"{_UNCLEAR_PREFIX} {raw}", False)

    hint = _after_colon(raw)
    if hint and len(hint) > 12 and _has_cyrillic_hint(hint):
        return (hint[:300], True)

    if (
        len(raw) <= 200
        and not raw.startswith("App\\")
        and _has_cyrillic_hint(raw)
        and not _looks_technical(raw)
    ):
        return (raw, True)

    return (f"{_UNCLEAR_PREFIX} {raw}", False)


def explain_dev_notes(
    issue: IssueRecord,
    what: str,
    *,
    is_clear: bool,
) -> tuple[list[str], str | None]:
    """Вопросы (0–2) или предположение о причине — не оба сразу."""
    raw = issue.title.strip()
    t = raw.lower()

    if what.startswith(_UNCLEAR_PREFIX):
        return _questions_for_unclear(raw, t), None

    if not is_clear:
        return _questions_for_unclear(raw, t), None

    hypothesis = _hypothesis(raw, t)
    return [], hypothesis


def _hypothesis(raw: str, t: str) -> str | None:
    compact = re.sub(r"\s+", "", t)
    if "syncadmissionvetmanagerjob" in compact or (
        "admission" in t and "sync" in t and "vetmanager" in t
    ):
        return (
            "Вероятно недоступен API Vetmanager, неверный токен клиники "
            "или расхождение данных приёма между виджетом и основной БД."
        )
    if "googlecalendar" in compact or ("google" in t and "calendar" in t):
        return (
            "Вероятно истёк OAuth-токен Google, отключён календарь "
            "или сбой на стороне Google Calendar API."
        )
    if "dev auth key" in t:
        return (
            "Вероятно в .env на этом окружении указан неверный или устаревший DEV_AUTH_KEY."
        )
    if "billing" in t:
        return "Вероятно billing API недоступен на тестовом стенде или неверный URL/ключ."
    if "cannot assign null" in t:
        return (
            "Вероятно фронт отправляет форму до заполнения обязательных полей "
            "или бэкенд не подставляет значение по умолчанию."
        )
    if "rabbitmq" in t:
        return "Вероятно брокер RabbitMQ не запущен или неверные host/port/credentials."
    if "clickhouse" in t:
        return "Вероятно ClickHouse недоступен или нет прав на запись — на UI не блокирует."
    if "integrity constraint" in t:
        return "Вероятно удаляют запись, на которую ссылаются другие таблицы."
    return None


def _questions_for_unclear(raw: str, t: str) -> list[str]:
    if "wazapa" in t:
        return [
            "Уточнить: WazapaGetStatus возвращает пустой {} — "
            "это проблема на стороне Wazapa API или наша?"
        ]
    if "wazapagetstatus" in re.sub(r"\s+", "", t):
        return [
            "Уточнить: что должен возвращать WazapaGetStatus и при каком сценарии в WhatsApp?"
        ]
    prefix = raw.split(":", 1)[0].strip() if ":" in raw else ""
    if prefix and len(prefix) < 80:
        return [
            f"Уточнить по «{prefix}»: при каком действии пользователя это возникает?",
        ]
    return [
        f"Что означает «{raw[:100]}{'…' if len(raw) > 100 else ''}» в продукте и как воспроизвести?",
    ]


def _after_colon(text: str) -> str:
    if ":" in text:
        part = text.split(":", 1)[1].strip()
        if len(part) > 3:
            return part
    if "—" in text:
        return text.split("—", 1)[1].strip()
    return ""


def _job_or_service_name(raw: str) -> str:
    if ":" in raw:
        name = raw.split(":", 1)[0].strip()
        if "job" in name.lower() or name.endswith("Job"):
            return f" в задаче {name}"
    return ""


def _looks_technical(raw: str) -> bool:
    markers = ("Exception", "Error", "TypeError", "CDb", "App\\", "stack", "PHP")
    return any(m in raw for m in markers)


def _has_cyrillic_hint(text: str) -> bool:
    return bool(re.search(r"[а-яА-ЯёЁ]", text))
