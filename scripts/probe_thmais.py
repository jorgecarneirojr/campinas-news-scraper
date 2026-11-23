"""Sonda o TH+ Mais através de um proxy brasileiro.

Uso (dentro do container do scraper):
    python scripts/probe_thmais.py

Descobre a URL do feed RSS e a estrutura das URLs de matéria, para calibrar
o spider. Requer um proxy BR válido (o site bloqueia IPs de datacenter).
"""

from __future__ import annotations

import asyncio
import re

import httpx

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PROXY = "http://189.90.248.95:8080"
HOME = "https://thmais.com.br/campinas/"


async def main() -> None:
    async with httpx.AsyncClient(
        proxy=PROXY,
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"},
    ) as client:
        resp = await client.get(HOME)
        html = resp.text
        print(f"home: status={resp.status_code} len={len(html)}")

        print("\n=== links RSS ===")
        for tag in re.findall(r"<link[^>]*application/rss\+xml[^>]*>", html)[:5]:
            print(" ", tag[:170])

        print("\n=== URLs de matéria ===")
        pattern = r'href="(https://thmais\.com\.br/campinas/[a-z0-9-]{15,}/)"'
        articles = list(dict.fromkeys(re.findall(pattern, html)))
        for url in articles[:8]:
            print(" ", url[:110])
        print(f"  total distintas: {len(articles)}")

        print("\n=== teste de feeds ===")
        for feed_url in (
            "https://thmais.com.br/campinas/feed/",
            "https://thmais.com.br/feed/",
        ):
            try:
                fr = await client.get(feed_url)
                is_rss = b"<rss" in fr.content[:2000]
                print(f"  {feed_url} -> {fr.status_code} len={len(fr.content)} rss={is_rss}")
                if is_rss:
                    items = re.findall(r"<item>(.*?)</item>", fr.text, re.S)
                    print(f"    itens: {len(items)}")
                    if items:
                        title = re.search(r"<title>(.*?)</title>", items[0], re.S)
                        link = re.search(r"<link>(.*?)</link>", items[0], re.S)
                        date = re.search(r"<pubDate>(.*?)</pubDate>", items[0], re.S)
                        print(f"    1º: {title.group(1)[:70] if title else '?'}")
                        print(f"        {link.group(1)[:90] if link else '?'}")
                        print(f"        {date.group(1) if date else '?'}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {feed_url} -> ERRO {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
