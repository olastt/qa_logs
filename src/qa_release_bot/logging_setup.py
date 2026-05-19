from __future__ import annotations

import logging
import sys

import structlog


def configure_console_encoding() -> None:
    """UTF-8 для stdout/stderr (emoji в отчёте на Windows cp1251)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def configure_logging(*, verbose: bool = False) -> None:
    """
    Логи — в stderr, отчёт — в stdout.

    По умолчанию (report) только warnings/errors, чтобы не ломать вывод отчёта.
    """
    configure_console_encoding()
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
