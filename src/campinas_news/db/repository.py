"""Repositório: toda a escrita/leitura de dados passa por aqui.

O upsert é feito com ``INSERT ... ON CONFLICT DO UPDATE`` do PostgreSQL,
o que torna a coleta idempotente e segura sob concorrência (vários workers
podem rodar em paralelo sem duplicar matérias).

Integração com o `clipping-tv`: as matérias web são casadas contra
``public.keywords WHERE kind='site'`` e gravadas em ``sites.article_keywords``,
o mesmo contrato de ``public.block_keywords``. Assim o `notify_worker` do
clipping-tv entrega matérias de portal sem nenhuma mudança de lógica.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from campinas_news.db.models import (
    Article,
    ArticleKeyword,
    ArticleRevision,
    ScrapeRun,
    ScrapeRunItem,
    Source,
    SourceHealth,
)
from campinas_news.scraping.models import ScrapedArticle, SourceDefinition


def _norm_kw(value: str) -> str:
    """Normaliza texto para casamento de palavra-chave (igual ao clipping-tv)."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z ]", " ", stripped)).strip()


def _kw_hit(hay_norm: str, needle_norm: str) -> bool:
    """Casa a palavra-chave como palavra/frase inteira (não substring)."""
    if not hay_norm or not needle_norm:
        return False
    return (
        re.search(r"(?<![0-9a-z])" + re.escape(needle_norm) + r"(?![0-9a-z])", hay_norm) is not None
    )


@dataclass(slots=True)
class UpsertOutcome:
    """Resultado do upsert de uma matéria."""

    article_id: int
    created: bool
    updated: bool

    @property
    def skipped(self) -> bool:
        return not self.created and not self.updated


class ArticleRepository:
    """Operações de persistência de matérias."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sync_sources(self, definitions: list[SourceDefinition]) -> None:
        """Garante que as fontes existam e estejam atualizadas."""
        for definition in definitions:
            stmt = (
                pg_insert(Source)
                .values(
                    slug=definition.slug,
                    name=definition.name,
                    base_url=definition.base_url,
                    strategy=definition.strategy,
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=[Source.slug],
                    set_={
                        "name": definition.name,
                        "base_url": definition.base_url,
                        "strategy": definition.strategy,
                        "is_active": True,
                        "updated_at": func.now(),
                    },
                )
            )
            await self._session.execute(stmt)

    async def upsert_article(self, article: ScrapedArticle) -> UpsertOutcome:
        """Insere ou atualiza uma matéria, criando revisão quando o conteúdo muda."""
        existing = await self._session.scalar(
            select(Article).where(
                Article.source_slug == article.source_slug,
                Article.url_hash == article.url_hash,
            )
        )

        if existing is None:
            row = Article(
                source_slug=article.source_slug,
                url=article.url,
                url_hash=article.url_hash,
                canonical_url=article.canonical_url,
                title=article.title,
                subtitle=article.subtitle,
                summary=article.summary,
                body_text=article.body_text,
                body_html=article.body_html,
                author=article.author,
                section=article.section,
                tags=list(article.tags),
                image_url=article.image_url,
                published_at=article.published_at,
                modified_at=article.modified_at,
                local_day=article.local_day,
                word_count=article.word_count,
                content_hash=article.content_hash,
                revision=1,
                raw_meta=article.raw_meta,
            )
            self._session.add(row)
            await self._session.flush()
            self._session.add(
                ArticleRevision(
                    article_id=row.id,
                    revision=1,
                    title=row.title,
                    body_text=row.body_text,
                    content_hash=row.content_hash,
                )
            )
            await self._session.flush()
            return UpsertOutcome(article_id=row.id, created=True, updated=False)

        if existing.content_hash == article.content_hash:
            existing.last_seen_at = func.now()
            await self._session.flush()
            return UpsertOutcome(article_id=existing.id, created=False, updated=False)

        existing.title = article.title
        existing.subtitle = article.subtitle
        existing.summary = article.summary
        existing.body_text = article.body_text
        existing.body_html = article.body_html
        existing.author = article.author
        existing.section = article.section
        existing.tags = list(article.tags)
        existing.image_url = article.image_url
        existing.published_at = article.published_at
        existing.modified_at = article.modified_at
        existing.local_day = article.local_day
        existing.word_count = article.word_count
        existing.content_hash = article.content_hash
        existing.revision += 1
        existing.last_seen_at = func.now()
        existing.raw_meta = article.raw_meta

        self._session.add(
            ArticleRevision(
                article_id=existing.id,
                revision=existing.revision,
                title=existing.title,
                body_text=existing.body_text,
                content_hash=existing.content_hash,
            )
        )
        await self._session.flush()
        return UpsertOutcome(article_id=existing.id, created=False, updated=True)

    async def rematch_all(self, *, day: date | None = None) -> int:
        """Recalcula `article_keywords` para matérias já coletadas.

        Necessário quando o catálogo de palavras-chave muda (ex.: keywords
        `kind='site'` criadas depois da coleta). Devolve quantas matérias
        ganharam ao menos um vínculo.
        """
        stmt = select(Article.id, Article.title, Article.summary)
        if day is not None:
            stmt = stmt.where(Article.local_day == day)
        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return 0

        keywords = (
            await self._session.execute(
                text("SELECT id, term FROM public.keywords WHERE active AND kind = 'site'")
            )
        ).all()
        if not keywords:
            return 0

        normalized = [(kid, _norm_kw(term)) for kid, term in keywords]
        touched = 0
        for article_id, title, summary in rows:
            blob = _norm_kw(f"{title or ''} {summary or ''}")
            hits = [kid for kid, needle in normalized if _kw_hit(blob, needle)]
            if not hits:
                continue
            await self._session.execute(
                pg_insert(ArticleKeyword)
                .values([{"article_id": article_id, "keyword_id": kid} for kid in hits])
                .on_conflict_do_nothing(
                    index_elements=[ArticleKeyword.article_id, ArticleKeyword.keyword_id]
                )
            )
            touched += 1
        await self._session.flush()
        return touched

    async def match_keywords(self, article_id: int, article: ScrapedArticle) -> int:
        """Casa a matéria contra `public.keywords` (kind='site') e grava os vínculos.

        Usa o MESMO algoritmo do clipping-tv (`_norm_kw` + `_kw_hit`): palavra
        inteira, sem substring, sem acento. Devolve quantos termos casaram.
        """
        rows = await self._session.execute(
            text("SELECT id, term FROM public.keywords " "WHERE active AND kind = 'site'")
        )
        keywords = rows.all()
        if not keywords:
            return 0

        blob = _norm_kw(f"{article.title} {article.summary or ''}")
        hits = [keyword_id for keyword_id, term in keywords if _kw_hit(blob, _norm_kw(term))]
        if not hits:
            return 0

        stmt = (
            pg_insert(ArticleKeyword)
            .values([{"article_id": article_id, "keyword_id": kid} for kid in hits])
            .on_conflict_do_nothing(
                index_elements=[ArticleKeyword.article_id, ArticleKeyword.keyword_id]
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return len(hits)

    async def known_url_hashes(self, source_slug: str, day: date) -> set[str]:
        """Hashes já coletados para a fonte no dia local (evita re-download)."""
        rows = await self._session.scalars(
            select(Article.url_hash).where(
                Article.source_slug == source_slug,
                Article.local_day == day,
            )
        )
        return set(rows.all())

    async def count_by_day(self, day: date) -> dict[str, int]:
        """Contagem de matérias por fonte em um dia local."""
        rows = await self._session.execute(
            select(Article.source_slug, func.count())
            .where(Article.local_day == day)
            .group_by(Article.source_slug)
        )
        return {slug: int(total) for slug, total in rows.all()}

    async def latest_articles(self, day: date, limit: int = 50) -> list[Article]:
        rows = await self._session.scalars(
            select(Article)
            .where(Article.local_day == day)
            .order_by(Article.published_at.desc().nullslast(), Article.id.desc())
            .limit(limit)
        )
        return list(rows.all())


class RunRepository:
    """Registro de execuções e saúde das fontes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start_run(self, run_id: str, trigger: str, sites_total: int) -> None:
        self._session.add(ScrapeRun(run_id=run_id, trigger=trigger, sites_total=sites_total))
        await self._session.flush()

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: datetime,
        duration_seconds: float,
        sites_ok: int,
        sites_failed: int,
        articles_found: int,
        articles_new: int,
        articles_updated: int,
        articles_skipped: int,
        errors: list[dict[str, Any]],
    ) -> None:
        run = await self._session.scalar(select(ScrapeRun).where(ScrapeRun.run_id == run_id))
        if run is None:
            return
        run.status = status
        run.finished_at = finished_at
        run.duration_seconds = duration_seconds
        run.sites_ok = sites_ok
        run.sites_failed = sites_failed
        run.articles_found = articles_found
        run.articles_new = articles_new
        run.articles_updated = articles_updated
        run.articles_skipped = articles_skipped
        run.errors = errors
        await self._session.flush()

    async def add_item(self, item: ScrapeRunItem) -> None:
        self._session.add(item)
        await self._session.flush()

    async def record_source_health(
        self, source_slug: str, *, ok: bool, error: str | None, at: datetime
    ) -> None:
        health = await self._session.scalar(
            select(SourceHealth).where(SourceHealth.source_slug == source_slug)
        )
        if health is None:
            health = SourceHealth(source_slug=source_slug)
            self._session.add(health)
            await self._session.flush()

        health.total_runs += 1
        if ok:
            health.last_success_at = at
            health.consecutive_failures = 0
            health.last_error = None
        else:
            health.last_failure_at = at
            health.total_failures += 1
            health.consecutive_failures += 1
            health.last_error = (error or "")[:2000]
        await self._session.flush()


async def ping(session: AsyncSession) -> bool:
    """Verifica conectividade com o banco."""
    result: int | None = await session.scalar(text("SELECT 1"))
    return result == 1
