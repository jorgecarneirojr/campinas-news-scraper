"""Logging estruturado com structlog.

Em produção emite JSON (uma linha por evento); em desenvolvimento usa
console colorido. O contexto de correlação (`run_id`, `site`) é propagado
via contextvars.
"""

from __future__ import annotations

import logging
import sys

import structlog

from campinas_news.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configura stdlib logging + structlog de forma idempotente."""
    level = getattr(logging, settings.log_level)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )
    # Bibliotecas verbosas
    for noisy in ("httpx", "httpcore", "asyncio", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if settings.log_json:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Retorna um logger structlog vinculado."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
