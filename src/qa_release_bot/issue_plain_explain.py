"""Human-readable issue explanation for QA reports."""

from __future__ import annotations

import re
from dataclasses import dataclass

from qa_release_bot.issue_record import IssueRecord


@dataclass(slots=True)
class TesterExplanation:
    one_liner: str
    why: str
    details: str


def explain_for_tester(issue: IssueRecord) -> TesterExplanation:
    corpus = _log_corpus(issue)
    low = corpus.lower()

    for rule in _RULES:
        one, why = rule(corpus, low, issue)
        if one:
            return TesterExplanation(
                one_liner=one,
                why=why,
                details=_details_tail(issue, corpus, one, why),
            )

    one = _fallback_one_liner(issue, corpus)
    why = _fallback_why(issue, corpus)
    return TesterExplanation(
        one_liner=one,
        why=why,
        details=_details_tail(issue, corpus, one, why),
    )


def _details_tail(issue: IssueRecord, corpus: str, one: str, why: str) -> str:
    bits: list[str] = []
    if issue.culprit and issue.culprit.lower() not in one.lower():
        bits.append(f"Контекст: {issue.culprit[:200]}.")
    excerpt = _message_excerpt(corpus, max_len=260)
    if excerpt and excerpt.lower() not in one.lower() and excerpt.lower() not in why.lower():
        bits.append(f"Фрагмент лога: {excerpt}")
    if issue.count > 1:
        bits.append(f"Повторялась {issue.count} раз.")
    return " ".join(bits)


def _log_corpus(issue: IssueRecord) -> str:
    parts = [issue.title or "", issue.culprit or ""]
    meta = issue.metadata or {}
    for key in ("type", "value", "title", "log_excerpt", "message"):
        val = meta.get(key)
        if val:
            parts.append(str(val))
    for msg in meta.get("log_messages") or []:
        parts.append(str(msg))
    for frame in issue.stack_frames or []:
        parts.append(frame.display())
    return "\n".join(p for p in parts if p.strip())


def _message_excerpt(corpus: str, *, max_len: int = 280) -> str:
    for line in corpus.splitlines():
        line = line.strip()
        if len(line) > 20:
            return line[:max_len]
    compact = re.sub(r"\s+", " ", corpus).strip()
    return compact[:max_len] if compact else ""


def _fallback_one_liner(issue: IssueRecord, corpus: str) -> str:
    text = _message_excerpt(corpus, max_len=180) or issue.title[:180]
    simplified = _simplify_technical(text)
    subject = _subject_from_issue(issue)
    if simplified:
        return f"{subject}: {simplified}"
    return f"{subject}: операция завершилась ошибкой"


def _fallback_why(issue: IssueRecord, corpus: str) -> str:
    low = corpus.lower()
    frequency = _frequency_hint(issue)

    if any(x in low for x in ("timeout", "timed out", "deadline", "execution time")):
        return (
            "Операция не успела завершиться за отведённое время. Обычно это бывает из-за "
            f"медленного запроса, внешнего сервиса или большой нагрузки. {frequency}"
        )
    if any(x in low for x in ("permission denied", "access denied", "forbidden", "unauthorized")):
        return (
            "Не хватило прав или не прошла авторизация. Проверьте пользователя, роль, токен "
            f"или доступ к ресурсу, на котором упало действие. {frequency}"
        )
    if any(x in low for x in ("not found", "404", "does not exist", "no such")):
        return (
            "Код попытался открыть объект, файл или страницу, которых нет в текущем окружении. "
            f"Нужно проверить входные данные и наличие объекта на стенде. {frequency}"
        )
    if any(x in low for x in ("null", "undefined", "missing", "empty")):
        return (
            "В обработку пришли неполные данные: какое-то поле пустое или отсутствует. "
            f"Чаще всего это связано с конкретной формой, API-запросом или миграцией данных. {frequency}"
        )
    if any(x in low for x in ("sql", "database", "mysql", "pgsql", "query")):
        return (
            "Падение связано с базой данных: запрос не выполнился или данные оказались не в том виде, "
            f"который ожидал код. {frequency}"
        )
    if any(x in low for x in ("connection", "connect", "network", "dns")):
        return (
            "Сервис не смог подключиться к другому сервису. Проверьте доступность адреса, порт, сеть "
            f"и настройки окружения. {frequency}"
        )

    return (
        "По логу видно место и симптом ошибки, но точная причина без сценария воспроизведения неочевидна. "
        f"Начните с проверки действия, которое выполнялось в этот момент, входных данных и окружения. {frequency}"
    )


def _frequency_hint(issue: IssueRecord) -> str:
    if issue.count <= 1:
        return "Сейчас это единичное срабатывание: стоит наблюдать, повторится ли."
    return f"Ошибка уже повторялась {issue.count} раз, поэтому её лучше завести в работу."


def _subject_from_issue(issue: IssueRecord) -> str:
    title = (issue.title or "").lower()
    culprit = (issue.culprit or "").lower()
    text = f"{title} {culprit}"
    if any(x in text for x in ("sync", "calendar", "job", "cron", "queue", "worker")):
        return "Фоновая задача не выполнилась"
    if any(x in text for x in ("api", "request", "controller", "action", "http")):
        return "Запрос пользователя завершился ошибкой"
    if any(x in text for x in ("save", "create", "update", "delete", "assign")):
        return "Данные не обработались корректно"
    return "Система зафиксировала ошибку"


def _simplify_technical(text: str) -> str:
    t = text.strip()
    replacements = (
        (r"Maximum execution time of (\d+) seconds exceeded", r"превышен лимит выполнения: \1 секунд"),
        (r"Allowed memory size of \d+ bytes exhausted", "закончилась память при обработке"),
        (r"Symfony\\Component\\ErrorHandler\\Error\\FatalError", "фатальная ошибка PHP"),
        (r"SQLSTATE\[[^\]]+\]", "ошибка базы данных"),
        (r"Exception|ErrorException|RuntimeException|FatalError", ""),
        (r"\\+", " "),
    )
    for pattern, repl in replacements:
        t = re.sub(pattern, repl, t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" :-")
    return t[:220]


def _extract_field(corpus: str, pattern: str) -> str:
    match = re.search(pattern, corpus, re.I)
    return match.group(1) if match else ""


def _rule_max_execution_time(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    match = re.search(r"maximum execution time of (\d+) second", low)
    if not match:
        return None, ""
    sec = match.group(1)
    if any(x in low for x in ("lock", "flock", "mutex", "waiting", "блокировк", "кеш", "cache")):
        return (
            f"Процесс завис на ожидании блокировки и был остановлен через {sec} секунд",
            "Обычно так бывает, когда несколько процессов одновременно работают с одними данными, кешем "
            "или очередью. Нужно проверить, что держит блокировку, и не запускаются ли параллельно тяжёлые задачи.",
        )
    return (
        f"Операция выполнялась слишком долго и была остановлена через {sec} секунд",
        "Чаще всего причина в медленном запросе к базе, долгом ответе внешнего сервиса, большом объёме данных "
        "или зависшем цикле. Для тестировщика важно найти действие и набор данных, на которых это повторяется.",
    )


def _rule_memory(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "allowed memory size" not in low and "memory exhausted" not in low:
        return None, ""
    return (
        "Операции не хватило памяти, поэтому обработка оборвалась",
        "Код загрузил или сформировал слишком много данных за один раз. Проверьте сценарии с большими списками, "
        "экспортами, отчётами, файлами или массовыми операциями.",
    )


def _rule_lock_timeout(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if not any(
        x in low
        for x in (
            "lock wait timeout",
            "could not obtain lock",
            "deadlock",
            "flock",
            "mutex",
            "блокировк",
        )
    ):
        return None, ""
    return (
        "Операция не дождалась доступа к данным и была отменена по таймауту",
        "Два процесса одновременно меняют одни данные или предыдущая операция зависла и держит блокировку. "
        "Проверьте массовые действия, повторные клики, фоновые задачи и параллельные запросы.",
    )


def _rule_connection(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if not any(x in low for x in ("connection refused", "could not connect", "connection timed out")):
        return None, ""
    where = "к внешнему сервису или базе данных"
    if "redis" in low:
        where = "к Redis"
    elif "rabbitmq" in low or "amqp" in low:
        where = "к RabbitMQ"
    elif "mysql" in low or "pgsql" in low or "database" in low:
        where = "к базе данных"
    return (
        f"Система не смогла подключиться {where}",
        "Сервис может быть остановлен, недоступен по сети, неправильно настроен в окружении или перегружен. "
        "Для проверки полезны время падения, стенд и действие, после которого пошёл запрос.",
    )


def _rule_rabbitmq(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "rabbitmq" not in low and "amqp" not in low:
        return None, ""
    return (
        "Фоновая очередь RabbitMQ недоступна, поэтому отложенные задачи не выполняются",
        "Проблема обычно в брокере очередей, настройках подключения или переполненной очереди. "
        "Пользователь может не увидеть ошибку сразу, но письма, синхронизации и фоновые операции могут не уйти.",
    )


def _rule_null_assign(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "cannot assign null" not in low:
        return None, ""
    field = _extract_field(c, r"property [\w\\]+::\$(\w+)")
    field_tail = f" `{field}`" if field else ""
    return (
        f"В обязательное поле{field_tail} пришло пустое значение, поэтому сохранение не прошло",
        "Форма или API передали неполные данные, либо backend не подставил значение по умолчанию. "
        "Проверьте конкретный экран, обязательные поля и сценарий сохранения.",
    )


def _rule_null_access(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if not any(
        x in low
        for x in (
            "call to a member function",
            "trying to get property",
            "attempt to read property",
            "on null",
            "null reference",
        )
    ):
        return None, ""
    return (
        "Код ожидал объект с данными, но получил пустое значение",
        "Такое бывает, когда запись не найдена, пользователь открыл устаревшую ссылку, данные удалили "
        "или API вернул неполный ответ. Проверьте сценарий с отсутствующими/удалёнными данными.",
    )


def _rule_undefined_key(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "undefined array key" not in low and "undefined index" not in low:
        return None, ""
    field = _extract_field(c, r"undefined (?:array key|index)[:\s]+['\"]?([\w.-]+)")
    field_tail = f" `{field}`" if field else ""
    return (
        f"В запросе или ответе не хватает поля{field_tail}, а код попытался его использовать",
        "Чаще всего это баг фронта или API: поле не передали, переименовали, сделали необязательным "
        "или сценарий не покрыт проверкой на пустые данные.",
    )


def _rule_sql(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "sqlstate" not in low and "database error" not in low and "mysql" not in low and "pgsql" not in low:
        return None, ""
    if any(x in low for x in ("duplicate", "unique constraint", "duplicate entry")):
        return (
            "Сохранение упало из-за дубля данных",
            "Система попыталась создать запись с уникальным значением, которое уже есть. "
            "Проверьте повторное сохранение, двойной клик, импорт и сценарии создания одинаковых объектов.",
        )
    if any(x in low for x in ("foreign key", "constraint fails")):
        return (
            "Сохранение упало из-за связанной записи, которой нет или которую нельзя удалить",
            "Данные ссылаются друг на друга: например, запись уже удалена, а другая всё ещё пытается её использовать. "
            "Проверьте порядок удаления/создания и связанные сущности.",
        )
    return (
        "Запрос к базе данных завершился ошибкой",
        "Причина в данных или структуре БД: не совпал формат, нет нужной записи, нарушено ограничение "
        "или запрос не поддержан текущей схемой. Нужны входные данные и шаги воспроизведения.",
    )


def _rule_http_5xx(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "server error" in low or "status code 5" in low or re.search(r"\bhttp\s*5\d\d\b", low):
        return (
            "Внешний или внутренний HTTP-сервис ответил серверной ошибкой",
            "Наша операция зависела от другого endpoint, а он вернул 5xx. Проверьте доступность сервиса, "
            "стенд, время падения и тело запроса, если оно есть в логах.",
        )
    return None, ""


def _rule_validation(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if not any(x in low for x in ("validation", "invalid argument", "invalid value", "bad request")):
        return None, ""
    return (
        "Система отклонила данные как некорректные",
        "В запросе пришёл неверный формат, недопустимое значение или не выполнено правило валидации. "
        "Проверьте поля формы/API и граничные значения.",
    )


_RULES = [
    _rule_max_execution_time,
    _rule_memory,
    _rule_lock_timeout,
    _rule_connection,
    _rule_rabbitmq,
    _rule_null_assign,
    _rule_null_access,
    _rule_undefined_key,
    _rule_sql,
    _rule_http_5xx,
    _rule_validation,
]
