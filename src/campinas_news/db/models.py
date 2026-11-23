"""Modelos ORM.

Decisões de engenharia:

* ``articles`` guarda a matéria canônica, uma linha por URL canônica.
  A chave de deduplicação é ``(source_slug, url_hash)`` — estável mesmo se a
  URL mudar de query string.
* ``article_revisions`` preserva o histórico: cada mudança de título/corpo
  gera uma nova revisão, permitindo auditoria e detecção de edições.
* ``scrape_runs`` e ``scrape_run_items`` registram a execução (observabilidade
  e idempotência: um item já coletado no mesmo dia não é re-baixado).
* ``source_health`` acumula métricas por fonte para alertas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarativa com convenção de nomes estável para constraints."""

    metadata = None  # type: ignore[assignment]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Source(Base, TimestampMixin):
    """Fonte (portal) de notícias."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    articles: Mapped[list[Article]] = relationship(back_populates="source")


class Article(Base, TimestampMixin):
    """Matéria canônica."""

    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("source_slug", "url_hash", name="uq_articles_source_url"),
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_local_day", "local_day"),
        Index("ix_articles_source_published", "source_slug", "published_at"),
        Index(
            "ix_articles_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_slug: Mapped[str] = mapped_column(
        String(64), ForeignKey("sources.slug", ondelete="RESTRICT"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1024))

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(256))
    section: Mapped[str | None] = mapped_column(String(128))
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024))

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Data local (America/Sao_Paulo) usada para "matérias do dia atual"
    local_day: Mapped[date] = mapped_column(Date, nullable=False)

    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    source: Mapped[Source] = relationship(back_populates="articles")
    revisions: Mapped[list[ArticleRevision]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleRevision(Base):
    """Snapshot de conteúdo de uma matéria (histórico de edições)."""

    __tablename__ = "article_revisions"
    __table_args__ = (UniqueConstraint("article_id", "revision", name="uq_revision_article_rev"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    article: Mapped[Article] = relationship(back_populates="revisions")


class ScrapeRun(Base):
    """Execução de coleta."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    sites_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sites_ok: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sites_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    items: Mapped[list[ScrapeRunItem]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ScrapeRunItem(Base):
    """Resultado por fonte dentro de uma execução."""

    __tablename__ = "scrape_run_items"
    __table_args__ = (Index("ix_run_items_run", "run_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scrape_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    source_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)

    run: Mapped[ScrapeRun] = relationship(back_populates="items")


class SourceHealth(Base, TimestampMixin):
    """Métricas acumuladas por fonte (para alertas de degradação)."""

    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
