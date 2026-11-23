"""Testes de extração dos spiders usando HTML de fixture (sem rede).

Cada fixture reproduz a estrutura real do portal, validada manualmente.
"""

from __future__ import annotations

from datetime import date

import pytest

from campinas_news.core.config import Settings
from campinas_news.scraping.feed import parse_feed
from campinas_news.scraping.fetcher import Fetcher
from campinas_news.scraping.spiders.acidadeon import ACidadeOnSpider
from campinas_news.scraping.spiders.brasil_campinas import BrasilCampinasSpider
from campinas_news.scraping.spiders.cbn_campinas import CbnCampinasSpider
from campinas_news.scraping.spiders.diario_campineiro import DiarioCampineiroSpider
from campinas_news.scraping.spiders.g1 import G1CampinasSpider
from campinas_news.scraping.spiders.hora_campinas import HoraCampinasSpider
from campinas_news.scraping.spiders.sampi import SampiCampinasSpider
from campinas_news.scraping.spiders.thmais import ThmaisCampinasSpider

DAY = date(2026, 11, 23)


class _StubFetcher(Fetcher):
    """Fetcher que devolve HTML pré-carregado, sem tocar na rede."""

    def __init__(self, settings: Settings, pages: dict[str, str]) -> None:
        super().__init__(settings)
        self._pages = pages

    async def get_text(self, url: str, *, use_cache: bool = True) -> str:
        if url not in self._pages:
            raise AssertionError(f"URL inesperada no teste: {url}")
        return self._pages[url]

    async def aclose(self) -> None:  # não fecha client real
        return None


def _spider(cls, settings: Settings, pages: dict[str, str]):
    return cls(settings, _StubFetcher(settings, pages))


@pytest.mark.asyncio
async def test_g1_extracts_article(settings: Settings, fixture_loader) -> None:
    url = "https://g1.globo.com/sp/campinas-regiao/noticia/2026/11/23/ia-recria-queda.ghtml"
    spider = _spider(G1CampinasSpider, settings, {url: fixture_loader("g1_article.html")})
    article = await spider.parse_article(url, day=DAY)

    assert article is not None
    assert article.source_slug == "g1-campinas"
    assert "Viracopos" in article.title
    assert article.body_text is not None
    assert "Comet 4" in article.body_text
    assert article.published_at is not None
    assert article.local_day == DAY
    assert article.word_count > 20
    assert article.content_hash


@pytest.mark.asyncio
async def test_hora_campinas_extracts_article(settings: Settings, fixture_loader) -> None:
    url = "https://horacampinas.com.br/deputada-federal-expoe-mensagem/"
    spider = _spider(HoraCampinasSpider, settings, {url: fixture_loader("hora_article.html")})
    # O fixture foi publicado em 22/11 (11:45 BRT)
    article = await spider.parse_article(url, day=date(2026, 11, 22))

    assert article is not None
    assert article.source_slug == "hora-campinas"
    assert article.body_text is not None
    assert "ameaça" in article.body_text.lower()
    assert article.published_at is not None


@pytest.mark.asyncio
async def test_acidadeon_extracts_paragraphs(settings: Settings, fixture_loader) -> None:
    url = (
        "https://www.acidadeon.com/campinas/cotidiano/"
        "mulher-e-atropelada-por-motociclista-ao-atravessar-avenida-fora-da-faixa/"
    )
    spider = _spider(ACidadeOnSpider, settings, {url: fixture_loader("acidadeon_article.html")})
    article = await spider.parse_article(url, day=DAY)

    assert article is not None
    assert article.source_slug == "acidadeon-campinas"
    assert article.body_text is not None
    assert "Emdec" in article.body_text
    assert "LEIA TAMBÉM" not in article.body_text
    assert article.published_at is not None
    assert article.published_at.isoformat() == "2026-11-23T12:19:31+00:00"


@pytest.mark.asyncio
async def test_sampi_extracts_split_body(settings: Settings, fixture_loader) -> None:
    url = (
        "https://sampi.net.br/campinas/noticias/3020350/campinas/2026/11/"
        "ciclista-morre-apos-ser-atingido-por-carro-em-jaguariuna"
    )
    spider = _spider(SampiCampinasSpider, settings, {url: fixture_loader("sampi_article.html")})
    article = await spider.parse_article(url, day=date(2026, 11, 22))

    assert article is not None
    assert article.source_slug == "sampi-campinas"
    assert article.body_text is not None
    # texto0 + texto1 devem estar presentes
    assert "reanimação cardiopulmonar" in article.body_text
    assert "perícia esteve no local" in article.body_text
    assert article.published_at is not None
    assert article.published_at.isoformat() == "2026-11-22T13:22:53+00:00"


@pytest.mark.asyncio
async def test_sampi_listing_discovery(settings: Settings, fixture_loader) -> None:
    spider = _spider(SampiCampinasSpider, settings, {})
    entries = spider.parse_listing(fixture_loader("sampi_listing.html"))
    assert entries
    assert all("/campinas/noticias/" in entry.url for entry in entries)
    assert len({entry.url for entry in entries}) == len(entries)


@pytest.mark.asyncio
async def test_cbn_extracts_article(settings: Settings, fixture_loader) -> None:
    url = "https://cbncampinas.com.br/2026/11/ponte-preta-negocia/"
    spider = _spider(CbnCampinasSpider, settings, {url: fixture_loader("cbn_article.html")})
    article = await spider.parse_article(url, day=DAY)

    assert article is not None
    assert article.source_slug == "cbn-campinas"
    assert article.body_text is not None
    assert "Ponte Preta" in article.body_text


@pytest.mark.asyncio
async def test_diario_campineiro_extracts_article(settings: Settings, fixture_loader) -> None:
    url = "https://diariocampineiro.com.br/unicamp-libera-consulta/"
    spider = _spider(DiarioCampineiroSpider, settings, {url: fixture_loader("diario_article.html")})
    article = await spider.parse_article(url, day=DAY)

    assert article is not None
    assert article.source_slug == "diario-campineiro"
    assert article.body_text is not None
    assert "Comvest" in article.body_text


@pytest.mark.asyncio
async def test_article_from_other_day_is_rejected(settings: Settings, fixture_loader) -> None:
    url = "https://cbncampinas.com.br/2026/11/ponte-preta-negocia/"
    spider = _spider(CbnCampinasSpider, settings, {url: fixture_loader("cbn_article.html")})
    article = await spider.parse_article(url, day=date(2026, 1, 1))
    assert article is None


# --- TH+ Mais -------------------------------------------------------------

THMAIS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Campinas terá câmeras para multar uso de celular</title>
    <link>https://thmais.com.br/campinas/campinas-tera-cameras-para-multar-uso-de-celular/</link>
    <pubDate>Mon, 23 Nov 2026 17:48:15 +0000</pubDate>
  </item>
  <item>
    <title>Criança sofre fratura em João Pessoa</title>
    <link>https://thmais.com.br/cidades/joao-pessoa/crianca-sofre-fratura/</link>
    <pubDate>Mon, 23 Nov 2026 17:40:00 +0000</pubDate>
  </item>
  <item>
    <title>Outra de Campinas</title>
    <link>https://thmais.com.br/campinas/outra-materia-de-campinas/</link>
    <pubDate>Mon, 23 Nov 2026 16:00:00 +0000</pubDate>
  </item>
</channel></rss>
"""


def test_thmais_filters_only_campinas(settings: Settings) -> None:
    """O feed global mistura praças; só Campinas deve passar."""
    spider = ThmaisCampinasSpider(settings, _StubFetcher(settings, {}))
    entries = parse_feed(THMAIS_FEED)
    assert len(entries) == 3

    filtered = spider.filter_entries(entries)
    assert len(filtered) == 2
    assert all("/campinas/" in e.url for e in filtered)
    assert not any("joao-pessoa" in e.url for e in filtered)


@pytest.mark.asyncio
async def test_thmais_extracts_article(settings: Settings, fixture_loader) -> None:
    url = "https://thmais.com.br/campinas/campinas-tera-cameras/"
    spider = _spider(ThmaisCampinasSpider, settings, {url: fixture_loader("thmais_article.html")})
    article = await spider.parse_article(url, day=DAY)

    assert article is not None
    assert article.source_slug == "thmais-campinas"
    assert article.body_text is not None
    assert "câmera" in article.body_text.lower()
    assert article.published_at is not None


# --- Brasil Campinas ------------------------------------------------------


@pytest.mark.asyncio
async def test_brasil_campinas_extracts_article(settings: Settings, fixture_loader) -> None:
    url = "https://brasilcampinas.com.br/carreta-de-mamografias/"
    spider = _spider(
        BrasilCampinasSpider, settings, {url: fixture_loader("brasil_campinas_article.html")}
    )
    article = await spider.parse_article(url, day=date(2022, 12, 2))

    assert article is not None
    assert article.source_slug == "brasil-campinas"
    assert article.body_text is not None
    assert "mamografia" in article.body_text.lower()


def test_brasil_campinas_definition(settings: Settings) -> None:
    """Registrado no registry, mas o site está parado desde 2022."""
    spider = BrasilCampinasSpider(settings, _StubFetcher(settings, {}))
    assert spider.definition.feed_url == "https://brasilcampinas.com.br/feed/"
    assert spider.definition.strategy == "rss"
