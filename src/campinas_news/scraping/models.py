"""Contratos de dados do pipeline de coleta.

Estes tipos são imutáveis e independentes do ORM: o spider produz
``ScrapedArticle`` e o repositório decide como persistir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

Strategy = Literal["rss", "html"]


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """Metadados estáticos de uma fonte."""

    slug: str
    name: str
    base_url: str
    strategy: Strategy
    feed_url: str | None = None
    listing_url: str | None = None


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """Item de um feed RSS/Atom, já normalizado."""

    url: str
    title: str | None = None
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    categories: tuple[str, ...] = ()
    image_url: str | None = None


@dataclass(frozen=True, slots=True)
class ListingEntry:
    """Link descoberto em uma página de listagem HTML."""

    url: str
    title: str | None = None


@dataclass(slots=True)
class ScrapedArticle:
    """Matéria pronta para persistência."""

    source_slug: str
    url: str
    url_hash: str
    title: str
    local_day: date
    content_hash: str
    canonical_url: str | None = None
    subtitle: str | None = None
    summary: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    author: str | None = None
    section: str | None = None
    tags: tuple[str, ...] = ()
    image_url: str | None = None
    published_at: datetime | None = None
    modified_at: datetime | None = None
    word_count: int = 0
    raw_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceResult:
    """Resultado da coleta de uma fonte."""

    source_slug: str
    status: Literal["ok", "partial", "failed"]
    found: int = 0
    new: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    duration_seconds: float = 0.0
    error: str | None = None
