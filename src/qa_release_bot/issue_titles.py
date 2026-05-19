"""Уникальные человекочитаемые названия issue для отчётов."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qa_release_bot.issue_record import IssueRecord
from qa_release_bot.module_map import ModuleResolution, resolve_module

_TITLE_MAX = 60


@dataclass
class IssueTitleRegistry:
    """Гарантирует уникальность tracker_title в рамках одного отчёта."""

    _counts: dict[str, int] = field(default_factory=dict)

    def unique(self, base: str, issue: IssueRecord) -> str:
        key = base.strip().lower()
        if key not in self._counts:
            self._counts[key] = 0
            return _truncate(base, _TITLE_MAX)
        self._counts[key] += 1
        hint = _disambiguator(issue)
        return _truncate(f"{base} — {hint}", _TITLE_MAX)


def glitchtip_issue_url(base_url: str, issue_id: str) -> str:
    root = (base_url or "").rstrip("/")
    if not root:
        return ""
    return f"{root}/issues/{issue_id}/"


def generate_tracker_title(
    issue: IssueRecord,
    resolution: ModuleResolution,
    registry: IssueTitleRegistry,
) -> str:
    tag = resolution.short_tag
    raw = issue.title.strip()
    base = _title_from_patterns(raw, tag, resolution, issue)
    return registry.unique(base, issue)


def _title_from_patterns(
    raw: str,
    tag: str,
    resolution: ModuleResolution,
    issue: IssueRecord,
) -> str:
    t = raw.lower()
    compact = re.sub(r"\s+", "", t)

    if "syncadmissionvetmanagerjob" in compact or (
        "admission" in t and "sync" in t and "failed" in t
    ):
        return f"[{tag}] Запись приёма не синхронизируется с Vetmanager"
    if "googlecalendarsyncschedulejob" in compact or (
        "google" in t and "calendar" in t and "sync" in t
    ):
        return f"[{tag}] Расписание не синхронизируется с Google Calendar"
    if "server error" in t and "get http" in t and "billing" in t:
        return f"[{tag}] Ошибка запроса к billing API"
    if "wrong dev auth key" in t or "dev auth key" in t:
        return f"[{tag}] Неверный ключ аутентификации разработчика"
    if "jsonapiwithcodeexception" in compact or "jsonapi" in t:
        hint = _after_colon(raw)
        if hint:
            return f"[{tag}] {_capitalize_first(hint[:50])}"
    if "rabbitmq" in t:
        return f"[{tag}] Фоновые задачи — очередь RabbitMQ недоступна"
    if "clickhouse" in t:
        return f"[{tag}] Аналитика — ClickHouse недоступен"
    if "file_put_contents" in t:
        return f"[{tag}] Ошибка записи служебного файла на сервере"
    if "cannot assign null" in t and "medicalcard" in t:
        return f"[{tag}] Не сохраняется медкарта — пустое поле"
    if "active record" in t and "новая" in t:
        return f"[{tag}] Невозможно удалить несохранённую запись"
    if "integrity constraint" in t or "1451" in t:
        return f"[{tag}] Ошибка связей в БД при сохранении"
    if "undefined array key" in t:
        return f"[{tag}] Неполные данные в форме или запросе"
    if "hasattribute" in t and "null" in t:
        return f"[{tag}] Сбой сохранения — данные не загрузились"
    if "prescription" in t:
        return f"[{tag}] Ошибка отправки рецепта"
    if "reportconstructor" in t or "report constructor" in t:
        return f"[{tag}] Ошибка при построении отчёта"

    if resolution.controller_key and not resolution.is_mapped:
        area = _controller_area_label(resolution.controller_key)
        return f"[{tag}] Ошибка в {area}"

    hint = _after_colon(raw)
    if hint and len(hint) > 8:
        return f"[{tag}] {_capitalize_first(hint[:48])}"

    short_raw = _shorten_technical_title(raw)
    if short_raw:
        return f"[{tag}] {short_raw}"

    return f"[{tag}] Сбой при выполнении действия"


def _controller_area_label(controller: str) -> str:
    name = controller.replace("Controller", "")
    if name.startswith("Frame") and len(name) > 5:
        rest = name[5:]
        if rest:
            return f"модуле приёмов ({rest})"
        return "модуле приёмов"
    areas = {
        "Dashly": "интеграции Dashly",
        "Widget": "виджетах",
        "Admission": "приёмах",
        "Client": "клиентах",
        "Reviews": "отзывах",
    }
    for key, label in areas.items():
        if key in name:
            return label
    return f"модуле {name[:24]}"


def _shorten_technical_title(raw: str) -> str:
    if "App\\Http\\Controllers\\" in raw or "App/Http/Controllers/" in raw:
        return ""
    if len(raw) > 80 and "Controller" in raw:
        m = re.search(r"([A-Za-z0-9]+Controller)", raw)
        if m:
            return _controller_area_label(m.group(1)).replace("модуле ", "модуле ")
    if len(raw) <= 55 and not raw.startswith("App\\"):
        return _capitalize_first(raw)
    return ""


def _disambiguator(issue: IssueRecord) -> str:
    hint = _after_colon(issue.title)
    if hint and len(hint) > 4:
        return _truncate(hint, 28)
    if issue.culprit:
        part = issue.culprit.replace("\\", "/").split("/")[-1]
        if part and part != issue.culprit:
            return _truncate(part.replace(".php", ""), 28)
    return f"id {issue.id}"


def _after_colon(text: str) -> str:
    if ":" in text:
        part = text.split(":", 1)[1].strip()
        if part.startswith("В") or len(part) > 3:
            return part[:80]
    if "—" in text:
        return text.split("—", 1)[1].strip()[:80]
    return ""


def _capitalize_first(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s[0].upper() + s[1:]


def _truncate(s: str, max_len: int) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def build_resolution(issue: IssueRecord, module_map: dict | None = None) -> ModuleResolution:
    return resolve_module(issue, module_map)
