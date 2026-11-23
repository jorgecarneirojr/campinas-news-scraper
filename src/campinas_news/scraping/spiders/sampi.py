"""Sampi Campinas.

Não possui feed RSS e responde **403** a requisições sem cabeçalhos de
navegador — o ``Fetcher`` já envia ``Accept``/``Accept-Language``/``User-Agent``
completos, o que resolve o bloqueio.

Descoberta: página ``/campinas/categoria/ultimas``.
URLs de matéria: ``/campinas/noticias/<id>/<secao>/<ano>/<mes>/<slug>``.
Corpo: ``.texto0`` + ``.texto1`` (o portal divide o texto em dois blocos).
Data: ``article:published_time`` (ISO 8601 com offset -03:00).
"""

from __future__ import annotations

from typing import ClassVar

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import SourceDefinition


class SampiCampinasSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="sampi-campinas",
        name="Sampi Campinas",
        base_url="https://sampi.net.br/campinas",
        strategy="html",
        listing_url="https://sampi.net.br/campinas/categoria/ultimas",
    )

    body_selectors: ClassVar[tuple[str, ...]] = (
        ".texto0",
        ".texto1",
    )
    title_selectors: ClassVar[tuple[str, ...]] = ("h1",)
    subtitle_selectors: ClassVar[tuple[str, ...]] = (".headline span",)
    author_selectors: ClassVar[tuple[str, ...]] = (".headline span",)
    section_selectors: ClassVar[tuple[str, ...]] = (".breadcrumb a",)
    image_selectors: ClassVar[tuple[str, ...]] = (
        'meta[property="og:image"]',
        "figure.capa img",
    )
    date_selectors: ClassVar[tuple[str, ...]] = (".headline time[datetime]", "time[datetime]")
    article_url_pattern: ClassVar[str] = r"/campinas/noticias/\d+/"

    def _extract_body_html(self, tree: HTMLParser) -> str | None:
        """O texto é dividido em ``.texto0`` e ``.texto1``; concatena na ordem."""
        fragments: list[str] = []
        for selector in self.body_selectors:
            for node in tree.css(selector):
                fragment = node.html
                if fragment and fragment.strip():
                    fragments.append(fragment)
        if not fragments:
            return super()._extract_body_html(tree)
        return "\n".join(fragments)
