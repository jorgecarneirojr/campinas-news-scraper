"""Fixtures compartilhadas."""

from __future__ import annotations

from pathlib import Path

import pytest

from campinas_news.core.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings() -> Settings:
    """Configuração determinística para testes (sem .env)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        log_json=False,
        postgres_password="test-password",
        scraper_min_delay=0.0,
        scraper_max_delay=0.0,
        scraper_max_attempts=1,
        scraper_max_articles_per_site=10,
    )


@pytest.fixture
def fixture_loader():
    """Carrega um arquivo de ``tests/fixtures``."""

    def _load(name: str) -> str:
        path = FIXTURES / name
        if not path.exists():
            pytest.skip(f"fixture ausente: {name}")
        return path.read_text(encoding="utf-8")

    return _load
