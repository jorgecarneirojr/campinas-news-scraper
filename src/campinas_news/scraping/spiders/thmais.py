"""TH+ Mais — Campinas (WordPress atrás de Cloudflare).

Particularidades:

* O site está protegido por **Cloudflare com bloqueio por IP** (403 em todas
  as URLs, inclusive na home). O ``Fetcher`` resolve isso via proxy com IP
  brasileiro — o host está em ``SCRAPER_BRAZIL_PROXY_HOSTS``.
* O feed específico de Campinas (``/campinas/feed/``) existe mas vem **vazio**.
  O feed global (``/feed/``) tem os itens de todas as praças (João Pessoa,
  Campinas, etc.), então filtramos por ``/campinas/`` na URL.
* O corpo fica em ``.entry-content`` (tema WordPress padrão).
"""

from __future__ import annotations

from typing import ClassVar

from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.models import FeedEntry, SourceDefinition


class ThmaisCampinasSpider(BaseSpider):
    definition: ClassVar[SourceDefinition] = SourceDefinition(
        slug="thmais-campinas",
        name="TH+ Mais Campinas",
        base_url="https://thmais.com.br/campinas/",
        strategy="rss",
        # Feed global: o de Campinas vem vazio. Filtramos por URL abaixo.
        feed_url="https://thmais.com.br/feed/",
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
    article_url_pattern: ClassVar[str] = r"^https://thmais\.com\.br/campinas/"

    def filter_entries(self, entries: list[FeedEntry]) -> list[FeedEntry]:
        """Mantém apenas matérias da praça de Campinas."""
        return [entry for entry in entries if "/campinas/" in entry.url]
