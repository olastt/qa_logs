"""Понятное объяснение лога для тестировщика (одна строка + почему появилась)."""

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
    corp_low = corpus.lower()

    for rule in _RULES:
        one, why = rule(corpus, corp_low, issue)
        if one:
            details = _details_tail(issue, corpus, one, why)
            return TesterExplanation(one_liner=one, why=why, details=details)

    one = _fallback_one_liner(issue, corpus)
    why = _fallback_why(issue, corpus)
    return TesterExplanation(
        one_liner=one,
        why=why,
        details=_details_tail(issue, corpus, one, why),
    )


def _details_tail(
    issue: IssueRecord, corpus: str, one: str, why: str
) -> str:
    bits: list[str] = []
    if issue.culprit and issue.culprit.lower() not in one.lower():
        bits.append(f"Контекст: {issue.culprit[:200]}.")
    excerpt = _message_excerpt(corpus, max_len=280)
    if excerpt and excerpt.lower() not in one.lower() and excerpt.lower() not in why.lower():
        bits.append(f"Из лога: {excerpt}")
    if issue.count > 1:
        bits.append(f"Повторялась {issue.count} раз.")
    return " ".join(bits)


def _log_corpus(issue: IssueRecord) -> str:
    parts = [issue.title or "", issue.culprit or ""]
    meta = issue.metadata or {}
    for key in ("type", "value", "title", "log_excerpt"):
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
    excerpt = _message_excerpt(corpus, max_len=200)
    if excerpt and _has_cyrillic(excerpt):
        return excerpt
    if excerpt:
        return _simplify_technical(excerpt)
    return f"Ошибка уровня {issue.level}: {issue.title[:160]}"


def _fallback_why(issue: IssueRecord, corpus: str) -> str:
    if issue.count == 1:
        return (
            "Сработала один раз — возможно разовый сбой, деплой или редкий сценарий. "
            "Если повторится, стоит эскалировать разработчикам."
        )
    return (
        f"Повторялась уже {issue.count} раз — значит проблема не единичная, "
        "нужно завести задачу и отслеживать после фикса."
    )


def _simplify_technical(text: str) -> str:
    t = text
    for pat, repl in (
        (r"Maximum execution time of \d+ seconds exceeded", "превышен лимит времени PHP"),
        (r"Symfony\\Component\\ErrorHandler\\Error\\FatalError", "фатальная ошибка PHP"),
        (r"\\+", " "),
    ):
        t = re.sub(pat, repl, t, flags=re.I)
    return t[:220].strip()


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яА-ЯёЁ]", text))


# --- правила: (corpus, corpus_lower, issue) -> (one_liner | None, why) ---


def _rule_max_execution_time(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    m = re.search(
        r"maximum execution time of (\d+) second",
        low,
    )
    if not m:
        return None, ""
    sec = m.group(1)
    if any(x in low for x in ("lock", "flock", "mutex", "waiting", "блокировк", "кеш", "cache")):
        return (
            f"Процесс завис на ожидании блокировки (часто кеш) — PHP оборвал выполнение через {sec} с",
            "Долгая операция не отпустила lock: параллельные запросы, тяжёлый кеш/Redis "
            "или зависший воркер. Нужно смотреть, кто держит блокировку и не упирается ли cron в тот же ресурс.",
        )
    return (
        f"Скрипт работал дольше {sec} секунд — PHP принудительно остановил выполнение",
        "Типично: тяжёлый запрос к БД, внешний API без ответа, бесконечный цикл или слишком "
        "много данных за один запрос. Повторяется при той же нагрузке или данных.",
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
        "Запрос не дождался блокировки в БД или кеше — операция отменена по таймауту",
        "Два процесса одновременно меняют одни данные, или предыдущая транзакция "
        "не завершилась. Часто всплывает при массовых задачах и параллельных кликах.",
    )


def _rule_connection(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "connection refused" in low or "could not connect" in low:
        where = "к внешнему сервису или БД"
        if "redis" in low:
            where = "к Redis"
        elif "rabbitmq" in low:
            where = "к RabbitMQ"
        elif "mysql" in low or "pgsql" in low:
            where = "к базе данных"
        return (
            f"Нет соединения {where} — хост недоступен или неверные настройки",
            "Сервис не запущен, сеть, firewall или неверный URL/порт в конфиге окружения. "
            "После рестарта инфраструктуры может пройти само.",
        )
    return None, ""


def _rule_rabbitmq(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "rabbitmq" not in low and "amqp" not in low:
        return None, ""
    return (
        "Фоновая очередь RabbitMQ недоступна — отложенные задачи не выполняются",
        "Брокер не запущен, неверные credentials или переполнена очередь. "
        "На UI пользователь может ничего не заметить, но письма/синхронизации не уйдут.",
    )


def _rule_null_assign(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "cannot assign null" not in low:
        return None, ""
    return (
        "В обязательное поле попало пустое значение — сохранение не прошло",
        "Форма отправила неполные данные или бэкенд не подставил значение по умолчанию. "
        "Воспроизводится на конкретном экране/действии.",
    )


def _rule_undefined_key(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "undefined array key" not in low and "undefined index" not in low:
        return None, ""
    m = re.search(r"undefined (?:array key|index)[:\s]+['\"]?(\w+)", c, re.I)
    field = f" «{m.group(1)}»" if m else ""
    return (
        f"В запросе не хватает поля{field} — сервер получил неполные данные",
        "Часто баг фронта или API: поле не передали, переименовали или сценарий не покрыт тестами.",
    )


def _rule_http_5xx(c: str, low: str, issue: IssueRecord) -> tuple[str | None, str]:
    if "server error" in low or "status code 5" in low or "http 5" in low:
        return (
            "Внешний HTTP-сервис ответил ошибкой — наша операция не завершилась",
            "Падение или перегрузка стороннего API (billing, интеграции). "
            "Проверить доступность сервиса на стенде.",
        )
    return None, ""


_RULES = [
    _rule_max_execution_time,
    _rule_lock_timeout,
    _rule_connection,
    _rule_rabbitmq,
    _rule_null_assign,
    _rule_undefined_key,
    _rule_http_5xx,
]
