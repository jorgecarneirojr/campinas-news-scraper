"""Classe base dos spiders.

O fluxo é sempre o mesmo:

1. **Descoberta** — ``discover()`` devolve candidatos (via RSS ou listagem HTML).
2. **Filtro** — descarta o que não é matéria do dia local ou já foi coletado.
3. **Extração** — ``parse_article()`` baixa a página e devolve ``ScrapedArticle``.
4. **Persistência** — o orquestrador faz o upsert.

Subclasses implementam apenas os seletores/particularidades do portal.
"""

from __future__ import annotations

import abc
import asyncio
from datetime import date, datetime
from typing import ClassVar

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from campinas_news.core.config import Settings
from campinas_news.core.logging import get_logger
from campinas_news.core.timeutil import local_day_bounds_utc, to_utc
from campinas_news.scraping.feed import parse_feed
from campinas_news.scraping.fetcher import Fetcher, FetchError
from campinas_news.scraping.models import (
    FeedEntry,
    ListingEntry,
    ScrapedArticle,
    SourceDefinition,
)
from campinas_news.scraping.normalize import (
    canonicalize_url,
    clean_text,
    content_hash,
    count_words,
    extract_canonical,
    extract_meta,
    find_json_ld_article,
    first_attr,
    first_text,
    html_to_text,
    sanitize_body_html,
    url_hash,
)

log = get_logger(__name__)


class BaseSpider(abc.ABC):
    """Contrato de um spider de portal."""

    definition: ClassVar[SourceDefinition]

    # Seletores sobrescritos pelas subclasses
    body_selectors: ClassVar[tuple[str, ...]] = ()
    title_selectors: ClassVar[tuple[str, ...]] = ("h1",)
    subtitle_selectors: ClassVar[tuple[str, ...]] = ()
    author_selectors: ClassVar[tuple[str, ...]] = ()
    section_selectors: ClassVar[tuple[str, ...]] = ()
    image_selectors: ClassVar[tuple[str, ...]] = ('meta[property="og:image"]',)
    date_selectors: ClassVar[tuple[str, ...]] = ()
    # Padrão que identifica uma URL de matéria (usado em listagens HTML)
    article_url_pattern: ClassVar[str] = ""

    def __init__(self, settings: Settings, fetcher: Fetcher) -> None:
        self.settings = settings
        self.fetcher = fetcher

    # -- descoberta ---------------------------------------------------------
    def filter_entries(self, entries: list[FeedEntry]) -> list[FeedEntry]:
        """Hook para filtrar itens do feed (ex.: só a praça de Campinas).

        A implementação padrão não filtra nada.
        """
        return entries

    async def discover(self, day: date) -> list[FeedEntry | ListingEntry]:
        """Descobre candidatos de matérias para o dia local informado."""
        definition = self.definition
        if definition.strategy == "rss" and definition.feed_url:
            xml_text = await self.fetcher.get_text(definition.feed_url)
            entries = self.filter_entries(parse_feed(xml_text))
            log.debug(
                "feed_parsed",
                site=definition.slug,
                entries=len(entries),
            )
            return list[FeedEntry | ListingEntry](entries)
        if definition.listing_url:
            html_text = await self.fetcher.get_text(definition.listing_url)
            return list[FeedEntry | ListingEntry](self.parse_listing(html_text))
        raise FetchError(definition.base_url, "fonte sem feed nem listagem configurada")

    def parse_listing(self, html_text: str) -> list[ListingEntry]:
        """Extrai links de matéria de uma página de listagem."""
        import re

        tree = HTMLParser(html_text)
        pattern = re.compile(self.article_url_pattern) if self.article_url_pattern else None
        seen: set[str] = set()
        entries: list[ListingEntry] = []

        for anchor in tree.css("a[href]"):
            href = anchor.attributes.get("href")
            if not href:
                continue
            absolute = canonicalize_url(href, base=self.definition.base_url)
            if pattern is not None and not pattern.search(absolute):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            entries.append(
                ListingEntry(
                    url=absolute,
                    title=clean_text(anchor.text(separator=" ", strip=True)),
                )
            )
        return entries

    # -- extração -----------------------------------------------------------
    async def parse_article(
        self, url: str, *, day: date, hint: FeedEntry | ListingEntry | None = None
    ) -> ScrapedArticle | None:
        """Baixa e extrai uma matéria. Retorna ``None`` se não for do dia."""
        html_text = await self.fetcher.get_text(url)
        tree = HTMLParser(html_text)

        json_ld = find_json_ld_article(tree) or {}
        published_at = self._extract_published_at(tree, json_ld)
        modified_at = self._extract_modified_at(tree, json_ld)

        if published_at is not None and not self._is_same_local_day(published_at, day):
            return None

        title = (
            self._json_ld_str(json_ld, "headline")
            or first_text(tree, self.title_selectors)
            or extract_meta(tree, property_name="og:title")
            or (hint.title if hint else None)
        )
        if not title:
            log.warning("article_without_title", site=self.definition.slug, url=url)
            return None

        hint_summary = hint.summary if isinstance(hint, FeedEntry) else None

        body_html = self._extract_body_html(tree)
        body_text = html_to_text(body_html) if body_html else None
        if not body_text:
            # Fallback: usa o resumo do feed
            body_text = clean_text(hint_summary)

        summary = (
            self._json_ld_str(json_ld, "description")
            or extract_meta(tree, property_name="og:description")
            or extract_meta(tree, property_name="description")
            or clean_text(hint_summary)
        )

        author = (
            self._json_ld_author(json_ld)
            or first_text(tree, self.author_selectors)
            or (hint.author if isinstance(hint, FeedEntry) else None)
        )
        section = self._json_ld_str(json_ld, "articleSection") or first_text(
            tree, self.section_selectors
        )
        image_url = (
            self._json_ld_image(json_ld)
            or first_attr(tree, self.image_selectors, "content")
            or first_attr(tree, self.image_selectors, "src")
            or (hint.image_url if isinstance(hint, FeedEntry) else None)
        )
        tags = self._extract_tags(tree, json_ld, hint)

        canonical = extract_canonical(tree) or url
        canonical_url = canonicalize_url(canonical, base=self.definition.base_url)
        local_day = (
            (published_at or datetime.now(tz=self.settings.tz)).astimezone(self.settings.tz).date()
        )

        return ScrapedArticle(
            source_slug=self.definition.slug,
            url=canonicalize_url(url, base=self.definition.base_url),
            url_hash=url_hash(url),
            canonical_url=canonical_url,
            title=clean_text(title) or title,
            subtitle=first_text(tree, self.subtitle_selectors),
            summary=clean_text(summary),
            body_text=body_text,
            body_html=sanitize_body_html(body_html),
            author=clean_text(author),
            section=clean_text(section),
            tags=tags,
            image_url=image_url,
            published_at=published_at,
            modified_at=modified_at,
            local_day=local_day,
            word_count=count_words(body_text),
            content_hash=content_hash(title, body_text),
            raw_meta={
                "strategy": self.definition.strategy,
                "json_ld_type": str(json_ld.get("@type")) if json_ld else None,
            },
        )

    # -- helpers de extração ------------------------------------------------
    def _extract_body_html(self, tree: HTMLParser) -> str | None:
        for selector in self.body_selectors:
            nodes = tree.css(selector)
            if not nodes:
                continue
            fragments = [node.html or "" for node in nodes]
            combined = "\n".join(fragment for fragment in fragments if fragment.strip())
            if combined.strip():
                return combined
        return None

    def _extract_published_at(
        self, tree: HTMLParser, json_ld: dict[str, object]
    ) -> datetime | None:
        candidates: list[str | None] = [
            self._json_ld_str(json_ld, "datePublished"),
            extract_meta(tree, property_name="article:published_time"),
            extract_meta(tree, property_name="og:published_time"),
        ]
        for selector in self.date_selectors:
            node = tree.css_first(selector)
            if node is not None:
                candidates.append(node.attributes.get("datetime") or node.text(strip=True))
        for raw in candidates:
            if raw:
                from campinas_news.core.timeutil import parse_datetime

                parsed = parse_datetime(raw, default_tz=self.settings.tz)
                if parsed is not None:
                    return parsed
        return None

    def _extract_modified_at(self, tree: HTMLParser, json_ld: dict[str, object]) -> datetime | None:
        from campinas_news.core.timeutil import parse_datetime

        raw = self._json_ld_str(json_ld, "dateModified") or extract_meta(
            tree, property_name="article:modified_time"
        )
        return parse_datetime(raw, default_tz=self.settings.tz) if raw else None

    def _extract_tags(
        self,
        tree: HTMLParser,
        json_ld: dict[str, object],
        hint: FeedEntry | ListingEntry | None,
    ) -> tuple[str, ...]:
        tags: list[str] = []
        keywords = self._json_ld_str(json_ld, "keywords")
        if keywords:
            tags.extend(part.strip() for part in keywords.split(",") if part.strip())
        if isinstance(hint, FeedEntry):
            tags.extend(hint.categories)
        for node in tree.css('meta[property="article:tag"]'):
            value = clean_text(node.attributes.get("content"))
            if value:
                tags.append(value)
        # Dedup preservando ordem
        return tuple(dict.fromkeys(tag for tag in tags if tag))

    def _is_same_local_day(self, moment: datetime, day: date) -> bool:
        start, end = local_day_bounds_utc(day, self.settings.tz)
        return start <= to_utc(moment) < end

    # -- helpers JSON-LD ----------------------------------------------------
    @staticmethod
    def _json_ld_str(json_ld: dict[str, object], key: str) -> str | None:
        value = json_ld.get(key)
        if isinstance(value, str):
            return clean_text(value)
        if isinstance(value, dict):
            nested = value.get("name") or value.get("@id")
            return clean_text(nested) if isinstance(nested, str) else None
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return clean_text(first)
            if isinstance(first, dict):
                nested = first.get("name")
                return clean_text(nested) if isinstance(nested, str) else None
        return None

    def _json_ld_author(self, json_ld: dict[str, object]) -> str | None:
        author = json_ld.get("author")
        if isinstance(author, dict):
            name = author.get("name")
            return clean_text(name) if isinstance(name, str) else None
        if isinstance(author, list):
            names = [
                clean_text(item.get("name"))
                for item in author
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            ]
            joined = ", ".join(name for name in names if name)
            return joined or None
        if isinstance(author, str):
            return clean_text(author)
        return None

    def _json_ld_image(self, json_ld: dict[str, object]) -> str | None:
        image = json_ld.get("image")
        if isinstance(image, str):
            return clean_text(image)
        if isinstance(image, dict):
            url = image.get("url")
            return clean_text(url) if isinstance(url, str) else None
        if isinstance(image, list) and image:
            first = image[0]
            if isinstance(first, str):
                return clean_text(first)
            if isinstance(first, dict):
                url = first.get("url")
                return clean_text(url) if isinstance(url, str) else None
        return None

    # -- orquestração -------------------------------------------------------
    async def collect(self, day: date, *, known_hashes: set[str]) -> list[ScrapedArticle]:
        """Coleta todas as matérias do dia, respeitando concorrência e limites."""
        candidates = await self.discover(day)
        limit = self.settings.scraper_max_articles_per_site
        if limit:
            candidates = candidates[:limit]

        semaphore = asyncio.Semaphore(self.settings.scraper_concurrency)
        results: list[ScrapedArticle] = []

        async def _process(candidate: FeedEntry | ListingEntry) -> ScrapedArticle | None:
            candidate_hash = url_hash(candidate.url)
            if candidate_hash in known_hashes:
                return None
            async with semaphore:
                try:
                    return await self.parse_article(candidate.url, day=day, hint=candidate)
                except FetchError as exc:
                    log.warning(
                        "article_fetch_failed",
                        site=self.definition.slug,
                        url=candidate.url,
                        error=str(exc),
                    )
                    return None
                except Exception as exc:
                    log.exception(
                        "article_parse_failed",
                        site=self.definition.slug,
                        url=candidate.url,
                        error=str(exc),
                    )
                    return None

        for article in await asyncio.gather(*(_process(item) for item in candidates)):
            if article is not None:
                results.append(article)
        return results
