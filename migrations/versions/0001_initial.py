"""schema inicial (acervo de portais no schema `sites`)

Quando integrado ao `clipping-tv`, o acervo TV/Rádio fica em `public` e o de
portais em `sites`. Rodando standalone, `sites` é o único schema usado.

Revision ID: 0001_initial
Revises: None
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "sites"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column(
            "source_slug",
            sa.String(64),
            sa.ForeignKey(f"{SCHEMA}.sources.slug", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("canonical_url", sa.String(1024)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("subtitle", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("body_text", sa.Text()),
        sa.Column("body_html", sa.Text()),
        sa.Column("author", sa.String(256)),
        sa.Column("section", sa.String(128)),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("image_url", sa.String(1024)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("modified_at", sa.DateTime(timezone=True)),
        sa.Column("local_day", sa.Date(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("raw_meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_slug", "url_hash", name="uq_articles_source_url"),
        schema=SCHEMA,
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"], schema=SCHEMA)
    op.create_index("ix_articles_local_day", "articles", ["local_day"], schema=SCHEMA)
    op.create_index(
        "ix_articles_source_published", "articles", ["source_slug", "published_at"], schema=SCHEMA
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_articles_title_trgm "
        f"ON {SCHEMA}.articles USING gin (title gin_trgm_ops)"
    )

    op.create_table(
        "article_revisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body_text", sa.Text()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("article_id", "revision", name="uq_revision_article_rev"),
        schema=SCHEMA,
    )

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default=sa.text("'running'")),
        sa.Column("sites_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sites_ok", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sites_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("articles_found", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("articles_new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("articles_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("articles_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("errors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("duration_seconds", sa.Float()),
        schema=SCHEMA,
    )

    op.create_table(
        "scrape_run_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey(f"{SCHEMA}.scrape_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_slug", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("found", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("error", sa.Text()),
        schema=SCHEMA,
    )
    op.create_index("ix_run_items_run", "scrape_run_items", ["run_id"], schema=SCHEMA)

    op.create_table(
        "source_health",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_slug", sa.String(64), nullable=False, unique=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )

    # Espelho de public.block_keywords: permite ao notify_worker do clipping-tv
    # entregar matérias de portal sem mudança de lógica.
    op.create_table(
        "article_keywords",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "keyword_id",
            sa.Integer(),
            sa.ForeignKey("public.keywords.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("article_id", "keyword_id", name="uq_article_keyword"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_article_keywords_article", "article_keywords", ["article_id"], schema=SCHEMA
    )
    op.create_index("ix_article_keywords_kw", "article_keywords", ["keyword_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("article_keywords", schema=SCHEMA)
    op.drop_table("source_health", schema=SCHEMA)
    op.drop_table("scrape_run_items", schema=SCHEMA)
    op.drop_table("scrape_runs", schema=SCHEMA)
    op.drop_table("article_revisions", schema=SCHEMA)
    op.drop_table("articles", schema=SCHEMA)
    op.drop_table("sources", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
