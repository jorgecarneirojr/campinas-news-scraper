"""Orquestrador de uma execução de coleta.

Garante:

* Um ``run_id`` único por execução (rastreável em logs e no banco).
* Isolamento de falhas: um portal quebrado não derruba os demais.
* Idempotência: matérias já coletadas no dia não são re-baixadas.
* Métricas agregadas persistidas em ``scrape_runs``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from campinas_news.core.config import Settings
from campinas_news.core.logging import get_logger
from campinas_news.core.timeutil import now_utc, today_local
from campinas_news.db.models import ScrapeRunItem
from campinas_news.db.repository import ArticleRepository, RunRepository
from campinas_news.db.session import session_scope
from campinas_news.scraping.fetcher import Fetcher
from campinas_news.scraping.models import SourceResult
from campinas_news.scraping.registry import all_definitions, build_spiders

log = get_logger(__name__)


class Collector:
    """Executa a coleta de todas as fontes habilitadas."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def run(self, *, trigger: str = "manual", day: date | None = None) -> str:
        """Executa uma coleta completa e devolve o ``run_id``."""
        target_day = day or today_local(self._settings.tz)
        run_id = f"{now_utc():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        started = time.perf_counter()

        log.info(
            "run_started",
            run_id=run_id,
            trigger=trigger,
            day=target_day.isoformat(),
            timezone=self._settings.app_timezone,
        )

        async with Fetcher(self._settings) as fetcher:
            spiders = build_spiders(self._settings, fetcher)
            if not spiders:
                log.warning("run_no_sources_enabled", run_id=run_id)
                return run_id

            async with session_scope(self._session_factory) as session:
                await ArticleRepository(session).sync_sources(all_definitions())
                await RunRepository(session).start_run(run_id, trigger, len(spiders))

            results = await asyncio.gather(
                *(self._collect_source(spider, run_id, target_day) for spider in spiders),
                return_exceptions=False,
            )

        duration = time.perf_counter() - started
        await self._finalize(run_id, results, duration)
        return run_id

    async def _collect_source(self, spider: object, run_id: str, day: date) -> SourceResult:
        """Coleta uma fonte em sua própria transação."""
        from campinas_news.scraping.base import BaseSpider

        assert isinstance(spider, BaseSpider)
        slug = spider.definition.slug
        started = time.perf_counter()
        result = SourceResult(source_slug=slug, status="ok")

        try:
            async with session_scope(self._session_factory) as session:
                articles_repo = ArticleRepository(session)
                known = await articles_repo.known_url_hashes(slug, day)
                articles = await spider.collect(day, known_hashes=known)

                result.found = len(articles)
                for article in articles:
                    outcome = await articles_repo.upsert_article(article)
                    if outcome.created:
                        result.new += 1
                    elif outcome.updated:
                        result.updated += 1
                    else:
                        result.skipped += 1
                    # Casa contra public.keywords (kind='site') para o
                    # notify_worker do clipping-tv entregar a matéria.
                    if outcome.created or outcome.updated:
                        await articles_repo.match_keywords(outcome.article_id, article)

                await RunRepository(session).record_source_health(
                    slug, ok=True, error=None, at=now_utc()
                )
        except Exception as exc:
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            log.exception("source_failed", run_id=run_id, site=slug, error=str(exc))
            async with session_scope(self._session_factory) as session:
                await RunRepository(session).record_source_health(
                    slug, ok=False, error=result.error, at=now_utc()
                )

        result.duration_seconds = round(time.perf_counter() - started, 3)
        log.info(
            "source_finished",
            run_id=run_id,
            site=slug,
            status=result.status,
            found=result.found,
            new=result.new,
            updated=result.updated,
            skipped=result.skipped,
            duration_s=result.duration_seconds,
        )
        return result

    async def _finalize(self, run_id: str, results: list[SourceResult], duration: float) -> None:
        sites_ok = sum(1 for item in results if item.status == "ok")
        sites_failed = sum(1 for item in results if item.status == "failed")
        errors = [{"site": item.source_slug, "error": item.error} for item in results if item.error]
        status = "success" if sites_failed == 0 else ("partial" if sites_ok else "failed")

        async with session_scope(self._session_factory) as session:
            runs = RunRepository(session)
            for item in results:
                await runs.add_item(
                    ScrapeRunItem(
                        run_id=run_id,
                        source_slug=item.source_slug,
                        status=item.status,
                        found=item.found,
                        new=item.new,
                        updated=item.updated,
                        skipped=item.skipped,
                        failed=item.failed,
                        duration_seconds=item.duration_seconds,
                        error=item.error,
                    )
                )
            await runs.finish_run(
                run_id,
                status=status,
                finished_at=now_utc(),
                duration_seconds=round(duration, 3),
                sites_ok=sites_ok,
                sites_failed=sites_failed,
                articles_found=sum(item.found for item in results),
                articles_new=sum(item.new for item in results),
                articles_updated=sum(item.updated for item in results),
                articles_skipped=sum(item.skipped for item in results),
                errors=errors,
            )

        log.info(
            "run_finished",
            run_id=run_id,
            status=status,
            sites_ok=sites_ok,
            sites_failed=sites_failed,
            articles_found=sum(item.found for item in results),
            articles_new=sum(item.new for item in results),
            articles_updated=sum(item.updated for item in results),
            duration_s=round(duration, 3),
        )
