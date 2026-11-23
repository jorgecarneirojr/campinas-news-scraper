"""Registro de spiders disponíveis.

Ponto único de extensão: para adicionar um portal, crie a classe em
``spiders/`` e registre-a aqui.
"""

from __future__ import annotations

from campinas_news.core.config import Settings
from campinas_news.scraping.base import BaseSpider
from campinas_news.scraping.fetcher import Fetcher
from campinas_news.scraping.models import SourceDefinition
from campinas_news.scraping.spiders.acidadeon import ACidadeOnSpider
from campinas_news.scraping.spiders.brasil_campinas import BrasilCampinasSpider
from campinas_news.scraping.spiders.cbn_campinas import CbnCampinasSpider
from campinas_news.scraping.spiders.diario_campineiro import DiarioCampineiroSpider
from campinas_news.scraping.spiders.g1 import G1CampinasSpider
from campinas_news.scraping.spiders.hora_campinas import HoraCampinasSpider
from campinas_news.scraping.spiders.sampi import SampiCampinasSpider
from campinas_news.scraping.spiders.thmais import ThmaisCampinasSpider

SPIDER_CLASSES: tuple[type[BaseSpider], ...] = (
    G1CampinasSpider,
    HoraCampinasSpider,
    ACidadeOnSpider,
    SampiCampinasSpider,
    CbnCampinasSpider,
    DiarioCampineiroSpider,
    ThmaisCampinasSpider,
    BrasilCampinasSpider,
)

SPIDERS_BY_SLUG: dict[str, type[BaseSpider]] = {cls.definition.slug: cls for cls in SPIDER_CLASSES}


def all_definitions() -> list[SourceDefinition]:
    """Definições de todas as fontes registradas."""
    return [cls.definition for cls in SPIDER_CLASSES]


def build_spiders(settings: Settings, fetcher: Fetcher) -> list[BaseSpider]:
    """Instancia os spiders habilitados pela configuração."""
    enabled = settings.enabled_sites
    selected = [cls for cls in SPIDER_CLASSES if not enabled or cls.definition.slug in enabled]
    unknown = set(enabled) - set(SPIDERS_BY_SLUG)
    if unknown:
        raise ValueError(
            f"SCRAPER_SITES contém slugs desconhecidos: {sorted(unknown)}. "
            f"Disponíveis: {sorted(SPIDERS_BY_SLUG)}"
        )
    return [cls(settings, fetcher) for cls in selected]
