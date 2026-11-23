"""A Cidade On — Campinas (WordPress/EPTV).

Feed: ``https://www.acidadeon.com/campinas/feed/`` (≈50 itens).
O corpo não tem container único: os parágrafos são ``p.wp-block-paragraph``
intercalados com blocos de anúncio (``.code-block``, ``.puddesk``), que são
removidos pela sanitização.
"""

from __future__ import annotations

from typing import ClassVar

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class ACidadeOnSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="acidadeon-campinas",
        name="A Cidade On Campinas",
        base_url="https://www.acidadeon.com/campinas/",
        strategy="rss",
        feed_url="https://www.acidadeon.com/campinas/feed/",
    )

    body_selectors: ClassVar[tuple[str, ...]] = (
        "section.s-content p.wp-block-paragraph",
        "p.wp-block-paragraph",
    )
    title_selectors: ClassVar[tuple[str, ...]] = (
        "h1.s-heading__title",
        "h1.entry-title",
        "h1",
    )
    subtitle_selectors: ClassVar[tuple[str, ...]] = (
        "h2.s-heading__subtitle",
        ".s-heading__subtitle",
    )
    author_selectors: ClassVar[tuple[str, ...]] = (
        ".s-heading__author",
        ".author",
        "[rel='author']",
    )
    section_selectors: ClassVar[tuple[str, ...]] = (
        ".s-heading__category",
        ".breadcrumb a",
    )
    image_selectors: ClassVar[tuple[str, ...]] = (
        'meta[property="og:image"]',
        "figure.s-heading__img img",
    )
    date_selectors: ClassVar[tuple[str, ...]] = ("time[datetime]",)
    article_url_pattern: ClassVar[str] = (
        r"^https://www\.acidadeon\.com/campinas/[a-z0-9-]+/[a-z0-9-]+/?$"
    )

    def _extract_body_html(self, tree: HTMLParser) -> str | None:
        """Concatena apenas os parágrafos de conteúdo, na ordem do documento."""
        paragraphs = tree.css("p.wp-block-paragraph")
        if not paragraphs:
            return super()._extract_body_html(tree)
        fragments = [node.html or "" for node in paragraphs]
        combined = "\n".join(fragment for fragment in fragments if fragment.strip())
        return combined or None
