"""Utilitários de data/hora com fuso explícito.

Regra do projeto: todo instante é armazenado em UTC (timestamptz) e todo
cálculo de "dia atual" usa o fuso de Campinas (America/Sao_Paulo).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

UTC = UTC


def now_utc() -> datetime:
    """Agora, em UTC e timezone-aware."""
    return datetime.now(tz=UTC)


def to_utc(value: datetime) -> datetime:
    """Normaliza um datetime para UTC. Datetimes naive são assumidos como UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(raw: str | None, *, default_tz: ZoneInfo | None = None) -> datetime | None:
    """Faz parsing tolerante de datas de feeds/HTML e devolve em UTC.

    Aceita RFC 822 (RSS), ISO 8601 (JSON-LD/meta) e formatos brasileiros
    comuns. Retorna ``None`` quando não for possível interpretar.
    """
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed: datetime = date_parser.parse(text, tzinfos=None)
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz or UTC)
    return parsed.astimezone(UTC)


def local_day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Intervalo [início, fim) do dia local, convertido para UTC."""
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def today_local(tz: ZoneInfo) -> date:
    """Data corrente no fuso informado."""
    return datetime.now(tz=tz).date()


def next_daily_run(now: datetime, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """Próxima ocorrência de HH:MM no fuso, retornada em UTC."""
    local_now = now.astimezone(tz)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)
