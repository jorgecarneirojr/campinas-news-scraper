"""Diário Campineiro (WordPress + Elementor).

Feed: ``https://diariocampineiro.com.br/feed/`` (10 itens).
O corpo é renderizado por um widget Elementor
(``.elementor-widget-theme-post-content``), então o seletor precisa ser
específico para não capturar listagens relacionadas.
"""

from __future__ import annotations

from typing import ClassVar

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class DiarioCampineiroSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="diario-campineiro",
        name="Diário Campineiro",
        base_url="https://diariocampineiro.com.br/",
        strategy="rss",
        feed_url="https://diariocampineiro.com.br/feed/",
    )

    body_selectors: ClassVar[tuple[str, ...]] = (
        ".elementor-widget-theme-post-content",
        ".entry-content",
        "article .post-content",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "h1.elementor-heading-title",
        "h1.entry-title",
        "h1",
    )
    subtitle_selectors: ClassVar[tuple[str, ...]] = (".elementor-widget-text-editor h2",)
    author_selectors: ClassVar[tuple[str, ...]] = (
        ".elementor-author-box__name",
        ".author-name",
        ".byline",
    )
    section_selectors: ClassVar[tuple[str, ...]] = (
        ".elementor-post-info__terms-list a",
        ".cat-links a",
    )
    image_selectors: ClassVar[tuple[str, ...]] = (
        'meta[property="og:image"]',
        ".elementor-widget-theme-post-featured-image img",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        ".elementor-post-info__item--type-date time[datetime]",
        "time[datetime]",
    )
    article_url_pattern: ClassVar[str] = r"^https://diariocampineiro\.com\.br/[a-z0-9-]+/?$"
