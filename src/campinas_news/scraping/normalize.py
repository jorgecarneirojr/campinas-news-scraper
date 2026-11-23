"""Normalização de texto, URLs e hashing.

Funções puras — testáveis sem rede nem banco.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

_WS_RE = re.compile(r"[\s\u00a0\u200b]+")
_DROP_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "amp")
_BLOCK_TAGS = ("script", "style", "noscript", "iframe", "form", "svg", "button", "aside")
# Parágrafos que são chamadas editoriais, não conteúdo da matéria
_BOILERPLATE_TEXT_RE = re.compile(
    r"^(leia\s+(tamb[ée]m|mais)|veja\s+tamb[ée]m|assista|ou[çc]a|"
    r"confira\s+(tamb[ée]m|mais)|saiba\s+mais|relacionad[oa]s?)\b",
    re.IGNORECASE,
)
_BOILERPLATE_SELECTORS = (
    ".publicidade",
    ".publi",
    ".ad",
    ".ads",
    ".advertisement",
    ".code-block",
    ".sharedaddy",
    ".share",
    ".compartilhar",
    ".related",
    ".leia-mais",
    ".newsletter",
    ".cookie",
    ".taboola",
    ".OUTBRAIN",
    "[class*='taboola']",
    "[id*='taboola']",
    "[class*='denakop']",
    "[id*='teads']",
    "[class*='newsletter']",
    "[class*='publicidade']",
)


def clean_text(value: str | None) -> str | None:
    """Colapsa espaços, remove caracteres invisíveis e entidades HTML."""
    if value is None:
        return None
    text = html.unescape(value)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def strip_accents(value: str) -> str:
    """Remove acentos (usado em comparações e slugs)."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slugify(value: str) -> str:
    text = strip_accents(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def canonicalize_url(url: str, *, base: str | None = None) -> str:
    """Normaliza uma URL: remove tracking, fragmento e barra final redundante."""
    absolute = urljoin(base, url.strip()) if base else url.strip()
    parts = urlsplit(absolute)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not key.lower().startswith(_DROP_QUERY_PREFIXES)
    ]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, urlencode(query_pairs), ""))


def url_hash(url: str) -> str:
    """Hash estável (sha256) da URL canônica."""
    return hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()


def content_hash(title: str, body_text: str | None) -> str:
    """Hash do conteúdo relevante para detectar edições."""
    payload = f"{clean_text(title) or ''}\x00{clean_text(body_text) or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def count_words(text: str | None) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b[\wÀ-ÿ'-]+\b", text))


def html_to_text(fragment: str | None) -> str | None:
    """Converte um fragmento HTML em texto puro, preservando parágrafos."""
    if not fragment:
        return None
    tree = HTMLParser(fragment)
    for tag in _BLOCK_TAGS:
        for node in tree.css(tag):
            node.decompose()
    for selector in _BOILERPLATE_SELECTORS:
        for node in tree.css(selector):
            node.decompose()

    paragraphs: list[str] = []
    for node in tree.css("p, h2, h3, li, blockquote"):
        text = clean_text(node.text(separator=" ", strip=True))
        if not text or len(text) <= 1:
            continue
        # Descarta chamadas editoriais ("LEIA TAMBÉM: ...", "Veja também: ...")
        if _BOILERPLATE_TEXT_RE.match(text):
            continue
        paragraphs.append(text)

    if not paragraphs:
        fallback = clean_text(tree.text(separator=" ", strip=True))
        return fallback

    # Remove duplicatas consecutivas (comum em portais com lazy-load)
    deduped: list[str] = []
    for paragraph in paragraphs:
        if not deduped or deduped[-1] != paragraph:
            deduped.append(paragraph)
    return "\n\n".join(deduped)


def sanitize_body_html(fragment: str | None) -> str | None:
    """Remove scripts/estilos e boilerplate do HTML do corpo."""
    if not fragment:
        return None
    tree = HTMLParser(fragment)
    for tag in _BLOCK_TAGS:
        for node in tree.css(tag):
            node.decompose()
    for selector in _BOILERPLATE_SELECTORS:
        for node in tree.css(selector):
            node.decompose()
    body = tree.body
    if body is None:
        return None
    result = body.html or ""
    return result.strip() or None


def extract_meta(tree: HTMLParser, *, property_name: str) -> str | None:
    """Lê ``<meta property=...>`` ou ``<meta name=...>``."""
    node = tree.css_first(f'meta[property="{property_name}"]')
    if node is None:
        node = tree.css_first(f'meta[name="{property_name}"]')
    if node is None:
        return None
    return clean_text(node.attributes.get("content"))


def extract_canonical(tree: HTMLParser) -> str | None:
    node = tree.css_first('link[rel="canonical"]')
    if node is None:
        return None
    return clean_text(node.attributes.get("href"))


def first_text(tree: HTMLParser, selectors: tuple[str, ...]) -> str | None:
    """Retorna o texto do primeiro seletor que casar."""
    for selector in selectors:
        node = tree.css_first(selector)
        if node is not None:
            text = clean_text(node.text(separator=" ", strip=True))
            if text:
                return text
    return None


def first_attr(tree: HTMLParser, selectors: tuple[str, ...], attribute: str) -> str | None:
    """Retorna o atributo do primeiro seletor que casar."""
    for selector in selectors:
        node = tree.css_first(selector)
        if node is not None:
            value = node.attributes.get(attribute)
            if value:
                return clean_text(value)
    return None


def extract_json_ld(tree: HTMLParser) -> list[dict[str, object]]:
    """Extrai todos os blocos JSON-LD válidos da página."""
    import json

    blocks: list[dict[str, object]] = []
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text(strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for candidate in candidates:
            if isinstance(candidate, dict):
                blocks.append(candidate)
                graph = candidate.get("@graph")
                if isinstance(graph, list):
                    blocks.extend(item for item in graph if isinstance(item, dict))
    return blocks


def find_json_ld_article(tree: HTMLParser) -> dict[str, object] | None:
    """Localiza o nó JSON-LD do tipo Article/NewsArticle."""
    for block in extract_json_ld(tree):
        node_type = block.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if any(
            str(item).lower() in {"article", "newsarticle", "reportagenewsarticle"}
            for item in types
        ):
            return block
    return None
