from __future__ import annotations

from datetime import date, datetime, timezone

_MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def fmt_date_ru(dt: datetime | date) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        d, m = dt.day, dt.month
    else:
        d, m = dt.day, dt.month
    return f"{d} {_MONTHS_RU[m - 1]}"


def fmt_datetime_ru(dt: datetime) -> str:
    """«18 мая в 17:20» — для last_seen в карточках."""
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc)
    return f"{dt.day} {_MONTHS_RU[dt.month - 1]} в {dt.hour:02d}:{dt.minute:02d}"


def fmt_date_ru_short(dt: datetime | date) -> str:
    """Для подписи периода: «19 мая 2026»."""
    if isinstance(dt, datetime):
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        return f"{dt.day} {_MONTHS_RU[dt.month - 1]} {dt.year}"
    return f"{dt.day} {_MONTHS_RU[dt.month - 1]} {dt.year}"
