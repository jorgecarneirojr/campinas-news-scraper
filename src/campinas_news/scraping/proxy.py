"""Pool de proxies com descoberta automática via ProxyScrape.

Motivação: alguns portais (Hora Campinas, CBN Campinas) bloqueiam o IP da
VPS com 403 — inclusive na home page, com User-Agent de navegador completo.
É bloqueio por IP/ASN, não por header. A saída é sair por outro IP.

Estratégia:

1. Baixa a lista pública do ProxyScrape (sem API key).
2. Embaralha e testa em paralelo contra uma URL de controle do próprio site
   alvo (o feed), exigindo HTTP 200 + corpo que pareça RSS.
3. Guarda os que passaram, com TTL. Quando o pool esvazia, renova.
4. O ``Fetcher`` usa o pool **apenas** para os hosts marcados como
   bloqueados; os demais seguem direto (mais rápido e mais confiável).

Proxies gratuitos são instáveis por natureza: o pool é tratado como
"melhor esforço" e a coleta continua funcionando sem ele (modo ``partial``).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from dataclasses import dataclass, field

import httpx

from campinas_news.core.logging import get_logger

log = get_logger(__name__)

PROXYSCRAPE_URL = (
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&protocol=http&proxy_format=ipport"
    "&format=text&timeout=5000"
)
# Lista restrita ao Brasil. Portais atrás de Cloudflare (TH+ Mais) só liberam
# IPs residenciais/ISP brasileiros — proxies de datacenter são bloqueados.
PROXYSCRAPE_URL_BR = (
    "https://api.proxyscrape.com/v4/free-proxy-list/get"
    "?request=display_proxies&country=br&protocol=http&proxy_format=ipport"
    "&format=text&timeout=10000"
)

# Corpo mínimo que indica que a resposta é um feed válido (não página de bloqueio)
_FEED_MARKERS = (b"<rss", b"<feed", b"<?xml")
# Marcadores da página de bloqueio do Cloudflare. Um proxy que devolve isso
# com HTTP 200 NÃO serve — precisa ser descartado.
_BLOCK_MARKERS = (
    b"you have been blocked",
    b"attention required",
    b"cf-error-details",
    b"enable javascript and cookies",
)


@dataclass(slots=True)
class ProxyPool:
    """Pool de proxies validados para um host específico."""

    host: str
    probe_url: str
    ttl_seconds: float = 1800.0
    max_candidates: int = 250
    concurrency: int = 60
    timeout: float = 12.0
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    # Quando True, usa a lista restrita ao Brasil. Necessário para portais
    # atrás de Cloudflare (TH+ Mais), que só liberam IPs residenciais BR.
    prefer_brazil: bool = False

    _valid: list[str] = field(default_factory=list)
    _built_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self._built_at) > self.ttl_seconds

    async def get(self) -> str | None:
        """Devolve um proxy válido, renovando o pool se necessário."""
        async with self._lock:
            if not self._valid or self.expired:
                await self._rebuild()
            if not self._valid:
                return None
            return random.choice(self._valid)  # noqa: S311 - balanceamento, não cripto

    def invalidate(self, proxy: str) -> None:
        """Remove um proxy que falhou no uso real."""
        with contextlib.suppress(ValueError):
            self._valid.remove(proxy)

    async def _rebuild(self) -> None:
        candidates = await self._fetch_candidates()
        if not candidates:
            log.warning("proxy_list_empty", host=self.host)
            self._valid = []
            self._built_at = time.monotonic()
            return

        valid = await self._probe_all(candidates)
        self._valid = valid
        self._built_at = time.monotonic()
        log.info(
            "proxy_pool_built",
            host=self.host,
            candidates=len(candidates),
            valid=len(valid),
        )

    async def _fetch_candidates(self) -> list[str]:
        url = PROXYSCRAPE_URL_BR if self.prefer_brazil else PROXYSCRAPE_URL
        try:
            async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                lines = [ln.strip() for ln in resp.text.splitlines() if ln.strip()]
        except Exception as exc:
            log.warning("proxy_list_failed", host=self.host, error=str(exc))
            return []

        # formato esperado: ip:porta
        candidates = [ln for ln in lines if ln.count(":") == 1]
        random.shuffle(candidates)
        return candidates[: self.max_candidates]

    async def _probe_all(self, candidates: list[str]) -> list[str]:
        semaphore = asyncio.Semaphore(self.concurrency)
        valid: list[str] = []

        async def probe(proxy: str) -> None:
            async with semaphore:
                if await self._probe_one(proxy):
                    valid.append(proxy)

        await asyncio.gather(*(probe(p) for p in candidates))
        return valid

    async def _probe_one(self, proxy: str) -> bool:
        try:
            async with httpx.AsyncClient(
                proxy=f"http://{proxy}",
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                },
            ) as client:
                resp = await client.get(self.probe_url)
                if resp.status_code != 200:
                    return False
                head = resp.content[:8000].lower()
                # Página de bloqueio do Cloudflare pode vir com HTTP 200.
                if any(marker in head for marker in _BLOCK_MARKERS):
                    return False
                # Aceita feed OU página HTML real (o probe pode ser a home).
                if any(marker in head for marker in _FEED_MARKERS):
                    return True
                return b"<html" in head and len(resp.content) > 20000
        except Exception:
            return False


class ProxyRegistry:
    """Mantém um ``ProxyPool`` por host bloqueado."""

    def __init__(self, user_agent: str, *, prefer_brazil_hosts: set[str] | None = None) -> None:
        self._user_agent = user_agent
        # Hosts que exigem IP brasileiro (Cloudflare com geo-bloqueio).
        self._prefer_brazil = prefer_brazil_hosts or set()
        self._pools: dict[str, ProxyPool] = {}

    def pool_for(self, host: str, probe_url: str) -> ProxyPool:
        pool = self._pools.get(host)
        if pool is None:
            pool = ProxyPool(
                host=host,
                probe_url=probe_url,
                user_agent=self._user_agent,
                prefer_brazil=host in self._prefer_brazil,
            )
            self._pools[host] = pool
        return pool
