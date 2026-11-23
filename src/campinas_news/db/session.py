"""Engine e fábrica de sessões assíncronas."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from campinas_news.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Cria o engine async com pool dimensionado e timeouts defensivos."""
    return create_async_engine(
        settings.database_url,
        echo=settings.postgres_echo,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "timeout": 10,
            "server_settings": {
                "application_name": "campinas-news-scraper",
                # O acervo de portais vive em `sites`, mas o scraper também
                # lê `public.keywords` (catálogo compartilhado com o
                # clipping-tv). Sem `public` no search_path, a query de
                # casamento de palavras-chave falha com UndefinedTable.
                "search_path": "sites,public",
            },
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transação por escopo: commit no sucesso, rollback na exceção."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
