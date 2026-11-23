"""Testes de datas, fusos e agendamento."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from campinas_news.core.timeutil import (
    local_day_bounds_utc,
    next_daily_run,
    parse_datetime,
    to_utc,
)

SP = ZoneInfo("America/Sao_Paulo")


@pytest.mark.parametrize(
    ("raw", "expected_iso"),
    [
        ("Mon, 23 Nov 2026 13:51:17 +0000", "2026-11-23T13:51:17+00:00"),
        ("2026-11-22T10:22:53-03:00", "2026-11-22T13:22:53+00:00"),
        ("2026-11-23T03:00:00.609-03:00", "2026-11-23T06:00:00.609000+00:00"),
    ],
)
def test_parse_datetime_returns_utc(raw: str, expected_iso: str) -> None:
    parsed = parse_datetime(raw)
    assert parsed is not None
    assert parsed.isoformat() == expected_iso
    assert parsed.tzinfo == UTC


def test_parse_datetime_naive_uses_default_tz() -> None:
    parsed = parse_datetime("2026-11-23 08:00:00", default_tz=SP)
    assert parsed is not None
    assert parsed.hour == 11  # 08:00 BRT == 11:00 UTC


@pytest.mark.parametrize("raw", [None, "", "   ", "não é data"])
def test_parse_datetime_invalid(raw: str | None) -> None:
    assert parse_datetime(raw) is None


def test_local_day_bounds_utc() -> None:
    start, end = local_day_bounds_utc(date(2026, 11, 23), SP)
    assert start.isoformat() == "2026-11-23T03:00:00+00:00"
    assert end.isoformat() == "2026-11-24T03:00:00+00:00"


def test_to_utc_assumes_utc_for_naive() -> None:
    naive = datetime(2026, 11, 23, 12, 0)
    assert to_utc(naive).isoformat() == "2026-11-23T12:00:00+00:00"


def test_next_daily_run_today_when_before_time() -> None:
    now = datetime(2026, 11, 23, 6, 0, tzinfo=UTC)  # 03:00 BRT
    result = next_daily_run(now, 6, 30, SP)
    assert result.isoformat() == "2026-11-23T09:30:00+00:00"


def test_next_daily_run_tomorrow_when_after_time() -> None:
    now = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)  # 12:00 BRT
    result = next_daily_run(now, 6, 30, SP)
    assert result.isoformat() == "2026-11-24T09:30:00+00:00"
