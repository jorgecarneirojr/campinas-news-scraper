"""Configuração tipada, carregada exclusivamente de variáveis de ambiente / .env.

Nenhum segredo é hardcoded. Falhas de configuração são detectadas na
inicialização (fail-fast) em vez de em tempo de execução.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_TIME_RE = re.compile(r"^(?P<h>[01]\d|2[0-3]):(?P<m>[0-5]\d)$")


class Settings(BaseSettings):
    """Configuração da aplicação."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Aplicação ---------------------------------------------------------
    app_env: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = True
    app_timezone: str = "America/Sao_Paulo"

    # --- Banco -------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "campinas_news"
    postgres_user: str = "campinas"
    postgres_password: SecretStr = SecretStr("")
    postgres_pool_size: int = 5
    postgres_max_overflow: int = 5
    postgres_echo: bool = False

    # --- Coleta ------------------------------------------------------------
    scraper_sites: str = ""
    scraper_concurrency: Annotated[int, Field(ge=1, le=32)] = 4
    scraper_min_delay: Annotated[float, Field(ge=0.0, le=60.0)] = 0.8
    scraper_max_delay: Annotated[float, Field(ge=0.0, le=120.0)] = 2.0
    scraper_timeout: Annotated[float, Field(gt=0, le=180)] = 25.0
    scraper_max_attempts: Annotated[int, Field(ge=1, le=10)] = 3
    scraper_max_articles_per_site: Annotated[int, Field(ge=0)] = 60
    scraper_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    scraper_proxy_url: str = ""
    # Hosts que exigem IP brasileiro (Cloudflare com geo-bloqueio).
    # Separados por vírgula, ex.: "thmais.com.br"
    scraper_brazil_proxy_hosts_raw: str = Field(
        default="thmais.com.br", alias="SCRAPER_BRAZIL_PROXY_HOSTS"
    )

    # --- Agendamento -------------------------------------------------------
    schedule_daily_at: str = "06:30"
    schedule_intraday_minutes: Annotated[int, Field(ge=0, le=1440)] = 120
    schedule_run_on_start: bool = True

    # --- Derivados ---------------------------------------------------------
    @field_validator("schedule_daily_at")
    @classmethod
    def _validate_daily_at(cls, value: str) -> str:
        if not _TIME_RE.match(value):
            raise ValueError("schedule_daily_at deve estar no formato HH:MM (00:00-23:59)")
        return value

    @field_validator("app_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"timezone inválido: {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _validate_delays(self) -> Settings:
        if self.scraper_max_delay < self.scraper_min_delay:
            raise ValueError("SCRAPER_MAX_DELAY deve ser >= SCRAPER_MIN_DELAY")
        return self

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def daily_at(self) -> tuple[int, int]:
        match = _TIME_RE.match(self.schedule_daily_at)
        assert match is not None  # garantido pelo validador
        return int(match.group("h")), int(match.group("m"))

    @property
    def scraper_brazil_proxy_hosts(self) -> tuple[str, ...]:
        """Hosts que exigem proxy com IP brasileiro."""
        return tuple(
            host.strip().lower()
            for host in self.scraper_brazil_proxy_hosts_raw.split(",")
            if host.strip()
        )

    @property
    def enabled_sites(self) -> tuple[str, ...]:
        """Lista de slugs habilitados; vazio significa 'todos'."""
        return tuple(slug.strip().lower() for slug in self.scraper_sites.split(",") if slug.strip())

    @property
    def database_url(self) -> str:
        """DSN async (asyncpg) para SQLAlchemy."""
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_safe(self) -> str:
        """DSN sem senha, seguro para logs."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:***"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """DSN síncrono usado pelo Alembic."""
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Configuração singleton (cacheada)."""
    return Settings()
