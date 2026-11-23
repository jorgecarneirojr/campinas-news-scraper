"""Hora Campinas (WordPress).

Feed: ``https://horacampinas.com.br/feed/`` (10 itens, sem paginação).
Corpo em ``.entry-content``; autor em ``.author``/``.entry-author``.
"""

from __future__ import annotations

from typing import ClassVar

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class HoraCampinasSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="hora-campinas",
        name="Hora Campinas",
        base_url="https://horacampinas.com.br/",
        strategy="rss",
        feed_url="https://horacampinas.com.br/feed/",
    )

    body_selectors: ClassVar[tuple[str, ...]] = (
        ".entry-content",
        "article .post-content",
        ".single-content",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "h1.entry-title",
        "h1.post-title",
        "h1",
    )
    subtitle_selectors: ClassVar[tuple[str, ...]] = ("h2.entry-subtitle", ".subtitle")
    author_selectors: ClassVar[tuple[str, ...]] = (
        ".author-name",
        ".entry-author",
        ".byline a",
    )
    section_selectors: ClassVar[tuple[str, ...]] = (
        ".cat-links a",
        ".entry-categories a",
    )
    image_selectors: ClassVar[tuple[str, ...]] = (
        'meta[property="og:image"]',
        ".entry-content img",
    )
    date_selectors: ClassVar[tuple[str, ...]] = ("time.entry-date[datetime]", "time[datetime]")
    article_url_pattern: ClassVar[str] = r"^https://horacampinas\.com\.br/[a-z0-9-]+/?$"
