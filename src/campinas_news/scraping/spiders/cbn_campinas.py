"""CBN Campinas 99,1 FM (WordPress).

Feed: ``https://cbncampinas.com.br/feed/`` (≈24 itens).
Corpo em ``.entry-content``; autor em ``dc:creator`` do feed.
"""

from __future__ import annotations

from typing import ClassVar

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class CbnCampinasSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="cbn-campinas",
        name="CBN Campinas 99,1 FM",
        base_url="https://cbncampinas.com.br/",
        strategy="rss",
        feed_url="https://cbncampinas.com.br/feed/",
    )

    body_selectors: ClassVar[tuple[str, ...]] = (
        ".entry-content",
        "article .post-content",
        ".single-post-content",
    )
    title_selectors: ClassVar[tuple[str, ...]] = ("h1.entry-title", "h1")
    subtitle_selectors: ClassVar[tuple[str, ...]] = (".entry-subtitle", "h2.subtitle")
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
    article_url_pattern: ClassVar[str] = r"^https://cbncampinas\.com\.br/\d{4}/\d{2}/"
