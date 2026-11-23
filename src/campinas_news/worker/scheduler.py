"""Loop de agendamento do worker.

Duas cadências:

* **Diária** — executa em ``SCHEDULE_DAILY_AT`` (fuso de Campinas).
* **Intraday** — a cada ``SCHEDULE_INTRADAY_MINUTES`` para capturar matérias
  publicadas ao longo do dia (0 desabilita).

O loop é cooperativo e cancelável: ``SIGTERM``/``SIGINT`` encerram a execução
corrente de forma limpa (``stop_grace_period`` no compose).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from campinas_news.core.config import Settings
from campinas_news.core.logging import get_logger
from campinas_news.core.timeutil import next_daily_run, now_utc
from campinas_news.worker.collector import Collector

log = get_logger(__name__)


class Scheduler:
    """Executa o ``Collector`` em intervalos configurados."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._collector = Collector(settings, session_factory)
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        """Loop principal."""
        self._install_signal_handlers()
        hour, minute = self._settings.daily_at

        if self._settings.schedule_run_on_start:
            await self._safe_run("startup")

        while not self._stop.is_set():
            now = now_utc()
            next_daily = next_daily_run(now, hour, minute, self._settings.tz)
            wake_at = next_daily

            if self._settings.schedule_intraday_minutes > 0:
                next_intraday = now + timedelta(minutes=self._settings.schedule_intraday_minutes)
                wake_at = min(wake_at, next_intraday)

            wait_seconds = max((wake_at - now).total_seconds(), 1.0)
            log.info(
                "scheduler_sleeping",
                wake_at=wake_at.isoformat(),
                wait_seconds=round(wait_seconds, 1),
            )

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait_seconds)
                break  # stop solicitado
            except TimeoutError:
                pass

            trigger = "daily" if wake_at == next_daily else "intraday"
            await self._safe_run(trigger)

        log.info("scheduler_stopped")

    async def _safe_run(self, trigger: str) -> None:
        try:
            await self._collector.run(trigger=trigger)
        except Exception as exc:
            log.exception("run_crashed", trigger=trigger, error=str(exc))

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.request_stop)


def describe_schedule(settings: Settings) -> str:
    """Descrição legível do agendamento (usada no log de boot)."""
    hour, minute = settings.daily_at
    intraday = (
        f"a cada {settings.schedule_intraday_minutes} min"
        if settings.schedule_intraday_minutes
        else "desabilitado"
    )
    return f"diário às {hour:02d}:{minute:02d} ({settings.app_timezone}); " f"intraday: {intraday}"


def _unused(_: datetime) -> None:  # pragma: no cover
    """Placeholder para manter import de datetime explícito no módulo."""
