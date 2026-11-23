"""CLI operacional (Typer).

Comandos:

* ``worker``      — loop de agendamento (usado pelo container).
* ``collect``     — coleta única (útil em cron externo ou debug).
* ``db-ping``     — verifica conectividade com o banco.
* ``healthcheck`` — verifica banco + última execução (usado no HEALTHCHECK).
* ``sources``     — lista as fontes registradas.
* ``stats``       — resumo de matérias por dia.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from campinas_news import __version__
from campinas_news.core.config import Settings, get_settings
from campinas_news.core.logging import configure_logging, get_logger
from campinas_news.core.timeutil import today_local
from campinas_news.db.repository import ArticleRepository, ping
from campinas_news.db.session import create_engine, create_session_factory, session_scope
from campinas_news.scraping.registry import all_definitions
from campinas_news.worker.collector import Collector
from campinas_news.worker.scheduler import Scheduler, describe_schedule

app = typer.Typer(
    name="campinas-news",
    help="Coleta diária de notícias dos portais de Campinas/SP.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
log = get_logger(__name__)


def _bootstrap() -> Settings:
    settings = get_settings()
    configure_logging(settings)
    return settings


def _parse_day(value: str | None, settings: Settings) -> date:
    if not value:
        return today_local(settings.tz)
    try:
        # Data pura (sem hora) — o fuso é aplicado depois em local_day_bounds_utc.
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("use o formato YYYY-MM-DD") from exc


@app.command()
def version() -> None:
    """Mostra a versão instalada."""
    console.print(f"campinas-news-scraper [bold]{__version__}[/bold]")


@app.command()
def worker() -> None:
    """Inicia o loop de agendamento (foreground)."""
    settings = _bootstrap()
    log.info(
        "worker_booting",
        version=__version__,
        schedule=describe_schedule(settings),
        database=settings.database_url_safe,
        sites=list(settings.enabled_sites) or "todos",
    )
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    async def _main() -> None:
        try:
            await Scheduler(settings, factory).run_forever()
        finally:
            await engine.dispose()

    asyncio.run(_main())


@app.command()
def collect(
    day: Annotated[
        str | None, typer.Option("--day", "-d", help="Dia local (YYYY-MM-DD). Padrão: hoje.")
    ] = None,
    trigger: Annotated[str, typer.Option(help="Rótulo da execução.")] = "cli",
) -> None:
    """Executa uma coleta única e encerra."""
    settings = _bootstrap()
    target = _parse_day(day, settings)
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    async def _main() -> str:
        try:
            return await Collector(settings, factory).run(trigger=trigger, day=target)
        finally:
            await engine.dispose()

    run_id = asyncio.run(_main())
    console.print(f"[green]coleta concluída[/green] run_id={run_id}")


@app.command("db-ping")
def db_ping() -> None:
    """Verifica se o banco responde."""
    settings = _bootstrap()
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    async def _main() -> bool:
        try:
            async with session_scope(factory) as session:
                return await ping(session)
        finally:
            await engine.dispose()

    ok = asyncio.run(_main())
    if not ok:
        raise typer.Exit(code=1)
    console.print("[green]banco OK[/green]")


@app.command()
def healthcheck() -> None:
    """Healthcheck do container: banco acessível."""
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    async def _main() -> bool:
        try:
            async with session_scope(factory) as session:
                return await ping(session)
        finally:
            await engine.dispose()

    try:
        ok = asyncio.run(_main())
    except Exception:
        raise typer.Exit(code=1) from None
    if not ok:
        raise typer.Exit(code=1)


@app.command()
def sources() -> None:
    """Lista as fontes registradas."""
    table = Table(title="Fontes registradas")
    table.add_column("slug", style="cyan")
    table.add_column("nome")
    table.add_column("estratégia")
    table.add_column("endpoint", overflow="fold")
    for definition in all_definitions():
        table.add_row(
            definition.slug,
            definition.name,
            definition.strategy,
            definition.feed_url or definition.listing_url or "-",
        )
    console.print(table)


@app.command()
def stats(
    day: Annotated[
        str | None, typer.Option("--day", "-d", help="Dia local (YYYY-MM-DD). Padrão: hoje.")
    ] = None,
) -> None:
    """Mostra a contagem de matérias por fonte em um dia."""
    settings = _bootstrap()
    target = _parse_day(day, settings)
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    async def _main() -> dict[str, int]:
        try:
            async with session_scope(factory) as session:
                return await ArticleRepository(session).count_by_day(target)
        finally:
            await engine.dispose()

    counts = asyncio.run(_main())
    table = Table(title=f"Matérias em {target.isoformat()} ({settings.app_timezone})")
    table.add_column("fonte", style="cyan")
    table.add_column("matérias", justify="right")
    for slug, total in sorted(counts.items()):
        table.add_row(slug, str(total))
    table.add_row("[bold]total[/bold]", f"[bold]{sum(counts.values())}[/bold]")
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
