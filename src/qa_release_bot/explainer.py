from __future__ import annotations

from dataclasses import dataclass

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.severity_rules import IssueSeverity


@dataclass(slots=True)
class IssueExplanation:
    what_happened: str
    where: str
    user_impact: str
    likely_cause: str
    qa_check: str


def explain_issue(issue: IssueRecord, severity: IssueSeverity) -> IssueExplanation:
    title = issue.title.lower()
    frame = _best_frame(issue)

    what = _what_happened(title, issue)
    where = _where_human(frame, issue)
    user_impact = _user_impact(title, issue)
    cause = _likely_cause(title, frame, issue)
    qa = _qa_scenario(title, issue)

    return IssueExplanation(
        what_happened=what,
        where=where,
        user_impact=user_impact,
        likely_cause=cause,
        qa_check=qa,
    )


def format_explanation(exp: IssueExplanation) -> str:
    lines = [
        f"🔍 **Что случилось:** {exp.what_happened}",
        f"📍 **Где:** {exp.where}",
        f"💥 **Что видит пользователь:** {exp.user_impact}",
        f"🔧 **Вероятная причина:** {exp.likely_cause}",
        f"✅ **Что проверить QA:** {exp.qa_check}",
    ]
    return "\n".join(lines)


def _best_frame(issue: IssueRecord):
    for f in issue.stack_frames:
        if f.in_app or "vetmanager" in (f.filename or "").lower():
            return f
    return issue.stack_frames[0] if issue.stack_frames else None


def _what_happened(title: str, issue: IssueRecord) -> str:
    if "cannot assign null" in title and "medicalcard" in title:
        return (
            "Система пытается сохранить медкарту, но обязательное поле (например, пациент) "
            "пришло пустым — запись не может быть создана."
        )
    if "active record" in title and "новая" in title:
        return (
            "Код пытается изменить или удалить запись в базе, которая ещё не была "
            "корректно сохранена."
        )
    if "integrity constraint" in title or "1451" in title:
        return "Операция в базе нарушает связи между таблицами (удаление или изменение «родительской» записи)."
    if "rabbitmq" in title:
        return "Фоновые задачи не могут подключиться к очереди сообщений — часть процессов не выполняется."
    if "undefined array key" in title:
        return "В запросе или форме не хватает ожидаемого поля — сервер получил неполные данные."
    if "hasattribute() on null" in title:
        return "Код обращается к объекту, который не был создан (пустая ссылка вместо данных)."
    return f"Зафиксирована ошибка уровня {issue.level}: {issue.title[:120]}."


def _where_human(frame, issue: IssueRecord) -> str:
    if frame and frame.function:
        name = frame.function.replace("::", " → ")
        module = _module_from_path(frame.filename)
        if module:
            return f"В модуле {module}, метод {name}"
        return f"В методе {name}"
    if issue.culprit:
        return f"В компоненте {issue.culprit}"
    return "Место не определено (см. стек в Glitchtip)"


def _module_from_path(path: str) -> str:
    p = (path or "").lower()
    if "prescription" in p:
        return "Prescriptions (рецепты)"
    if "medicalcard" in p:
        return "MedicalCard (медкарта)"
    if "invoice" in p:
        return "Счета / Invoice"
    if "erest" in p:
        return "REST API"
    if "reportconstructor" in p:
        return "Конструктор отчётов"
    return ""


def _user_impact(title: str, issue: IssueRecord) -> str:
    if "medicalcard" in title:
        return "Не открывается или не сохраняется медкарта / приём."
    if "prescription" in title:
        return "Не создаётся или не отправляется рецепт."
    if "invoice" in title:
        return "Проблемы со счетом, оплатой или печатью документов."
    if "rabbitmq" in title:
        return "Задержки фоновых операций; UI может работать, но задачи «зависают»."
    if issue.level == "fatal":
        return "Экран с ошибкой или белая страница в сценарии."
    return "Сообщение об ошибке, неполное сохранение данных или сбой действия."


def _likely_cause(title: str, frame, issue: IssueRecord) -> str:
    if "cannot assign null" in title:
        return "Не передаётся ID пациента/приёма или сбой валидации на stage."
    if "rabbitmq" in title:
        return "Неверный хост очереди или сервис RabbitMQ недоступен на stage."
    if frame:
        return f"Исключение в {frame.display()} — проверить входные данные и конфиг окружения."
    return "Требуется разбор стека и сравнение с test."


def _qa_scenario(title: str, issue: IssueRecord) -> str:
    if "medicalcard" in title:
        return "Создать приём с минимальным набором полей и без пациента → сохранить медкарту на stage."
    if "prescription" in title:
        return "Выписать рецепт из карточки пациента на stage, проверить ответ внешнего API."
    if "undefined array key" in title and "quantity" in title:
        return "Создать счёт/документ с позициями без количества — проверить валидацию формы."
    if "rabbitmq" in title:
        return "Запустить фоновую задачу (очередь) и проверить доступность RabbitMQ с pod stage."
    return f"Воспроизвести сценарий по title на stage; issue id={issue.id} в Glitchtip."
