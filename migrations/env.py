"""Ambiente Alembic (síncrono, via psycopg).

A URL vem de ``Settings`` — nunca do ``alembic.ini`` — para que a senha
permaneça apenas em variáveis de ambiente.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool, text

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from campinas_news.core.config import get_settings  # noqa: E402
from campinas_news.db.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    settings = get_settings()
    # psycopg3 síncrono para o Alembic
    password = settings.postgres_password.get_secret_value()
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


# O scraper compartilha o banco com o clipping-tv, que já usa a tabela
# `alembic_version` para as próprias migrações (0001..0018). Usar a mesma
# tabela faria os dois projetos sobrescreverem a versão um do outro.
# Por isso o scraper mantém a sua em `sites.alembic_version`.
VERSION_TABLE = "alembic_version"
VERSION_TABLE_SCHEMA = "sites"


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table=VERSION_TABLE,
        version_table_schema=VERSION_TABLE_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        # O schema precisa existir antes do Alembic criar a tabela de versão.
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {VERSION_TABLE_SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table=VERSION_TABLE,
            version_table_schema=VERSION_TABLE_SCHEMA,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
