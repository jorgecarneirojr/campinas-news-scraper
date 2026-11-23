"""Rádio Brasil Campinas — AM 1270 (WordPress).

Feed: ``https://brasilcampinas.com.br/feed/``.

**Atenção operacional:** o site está sem publicações desde 02/12/2022
(confirmado pelo feed RSS e pela WP REST API). A coleta funciona, mas o
filtro de "dia atual" descarta tudo — o resultado é sempre 0 matérias.
Mantido no registry para o caso de o portal ser reativado.
"""

from __future__ import annotations

from typing import ClassVar

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class BrasilCampinasSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="brasil-campinas",
        name="Rádio Brasil Campinas",
        base_url="https://brasilcampinas.com.br/",
        strategy="rss",
        feed_url="https://brasilcampinas.com.br/feed/",
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
        ".author.vcard a",
        ".entry-author",
        ".byline",
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
    article_url_pattern: ClassVar[str] = r"^https://brasilcampinas\.com\.br/[a-z0-9-]+/?$"
