"""Cliente HTTP assíncrono com retry, backoff, rate-limit por host e cache.

Responsabilidades:

* Um único ``httpx.AsyncClient`` compartilhado (pool de conexões HTTP/2).
* Retry exponencial com jitter em erros transitórios (5xx, 429, timeouts).
* Rate-limit cooperativo por host (delay aleatório entre requisições).
* Cache em memória por execução: a mesma URL não é baixada duas vezes.
* Respeito a ``Retry-After``.
"""

from __future__ import annotations

import asyncio
import random
from collections import defaultdict
from types import TracebackType

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from campinas_news.core.config import Settings
from campinas_news.core.logging import get_logger

log = get_logger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 522, 524})


class FetchError(RuntimeError):
    """Falha definitiva ao obter uma URL."""

    def __init__(self, url: str, reason: str, status: int | None = None) -> None:
        self.url = url
        self.reason = reason
        self.status = status
        super().__init__(f"{reason} ({status}) para {url}" if status else f"{reason} para {url}")


class _RetryableHTTPError(Exception):
    def __init__(self, status: int, retry_after: float | None = None) -> None:
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"HTTP {status}")


class Fetcher:
    """Cliente HTTP com políticas de resiliência."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.scraper_timeout),
            follow_redirects=True,
            http2=True,
            headers={
                "User-Agent": settings.scraper_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            },
            proxy=settings.scraper_proxy_url or None,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request_at: dict[str, float] = {}
        self._cache: dict[str, str] = {}

    # -- ciclo de vida ------------------------------------------------------
    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- API ----------------------------------------------------------------
    async def get_text(self, url: str, *, use_cache: bool = True) -> str:
        """Baixa uma URL e devolve o corpo como texto."""
        if use_cache and url in self._cache:
            return self._cache[url]

        host = httpx.URL(url).host
        async with self._host_locks[host]:
            await self._respect_rate_limit(host)
            body = await self._get_with_retry(url)
            self._last_request_at[host] = asyncio.get_running_loop().time()

        if use_cache:
            self._cache[url] = body
        return body

    # -- internos -----------------------------------------------------------
    async def _respect_rate_limit(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is None:
            return
        elapsed = asyncio.get_running_loop().time() - last
        # Jitter de rate-limit: não é uso criptográfico.
        delay = random.uniform(  # noqa: S311
            self._settings.scraper_min_delay, self._settings.scraper_max_delay
        )
        remaining = delay - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _get_with_retry(self, url: str) -> str:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._settings.scraper_max_attempts),
                # Backoff generoso: portais como o Sampi aplicam 429 agressivo.
                wait=wait_exponential_jitter(initial=2, max=45, jitter=2),
                retry=retry_if_exception_type(
                    (_RetryableHTTPError, httpx.TransportError, httpx.TimeoutException)
                ),
                reraise=True,
            ):
                with attempt:
                    return await self._single_request(url)
        except _RetryableHTTPError as exc:
            raise FetchError(url, "status não recuperável após retries", exc.status) from exc
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise FetchError(url, f"erro de transporte: {exc}") from exc
        except RetryError as exc:  # pragma: no cover - defensivo
            raise FetchError(url, "retries esgotados") from exc
        raise FetchError(url, "estado inesperado")  # pragma: no cover

    async def _single_request(self, url: str) -> str:
        response = await self._client.get(url)
        if response.status_code in RETRYABLE_STATUS:
            retry_after = response.headers.get("Retry-After")
            delay: float | None = None
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = None
            if delay:
                await asyncio.sleep(min(delay, 30))
            log.warning("http_retryable_status", url=url, status=response.status_code)
            raise _RetryableHTTPError(response.status_code, delay)

        if response.status_code >= 400:
            raise FetchError(url, "resposta de erro", response.status_code)

        response.encoding = response.encoding or "utf-8"
        return response.text
