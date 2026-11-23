"""G1 — Campinas e Região (Globo).

Feed oficial: ``https://g1.globo.com/rss/g1/sp/campinas-regiao/`` (≈100 itens).
O corpo fica em ``.mc-article-body`` com parágrafos ``.content-text__container``.
O G1 não expõe ``article:published_time`` em meta; a data vem do JSON-LD
(``datePublished``) e, como fallback, do ``<time datetime>`` do cabeçalho.
"""

from __future__ import annotations

from typing import ClassVar

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class G1CampinasSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="g1-campinas",
        name="G1 Campinas e Região",
        base_url="https://g1.globo.com/sp/campinas-regiao/",
        strategy="rss",
        feed_url="https://g1.globo.com/rss/g1/sp/campinas-regiao/",
    )

    body_selectors: ClassVar[tuple[str, ...]] = (
        ".mc-article-body",
        "article .content-text__container",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "h1.content-head__title",
        "h1",
    )
    subtitle_selectors: ClassVar[tuple[str, ...]] = (
        "h2.content-head__subtitle",
        ".content-head__subtitle",
    )
    author_selectors: ClassVar[tuple[str, ...]] = (
        ".content-publication-data__from",
        "[class*='content-publication-data'] a",
    )
    section_selectors: ClassVar[tuple[str, ...]] = (
        ".header-title__text",
        "nav.breadcrumb a",
    )
    image_selectors: ClassVar[tuple[str, ...]] = (
        'meta[property="og:image"]',
        "figure img",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (
        "time[datetime]",
        ".content-publication-data__updated time",
    )
    article_url_pattern: ClassVar[str] = r"/noticia/\d{4}/\d{2}/\d{2}/"
