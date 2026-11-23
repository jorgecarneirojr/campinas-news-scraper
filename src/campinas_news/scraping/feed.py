"""Parser de feeds RSS 2.0 / Atom.

Usa ``xml.etree`` (stdlib) com proteção contra entidades externas e
tolerância a feeds malformados — comum em portais WordPress.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from campinas_news.core.timeutil import parse_datetime
from campinas_news.scraping.models import FeedEntry
from campinas_news.scraping.normalize import clean_text, html_to_text

_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}

_IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return clean_text(node.text)


def _first_image(html_fragment: str | None) -> str | None:
    if not html_fragment:
        return None
    match = _IMG_SRC_RE.search(html_fragment)
    return clean_text(match.group(1)) if match else None


def parse_feed(xml_text: str) -> list[FeedEntry]:
    """Converte o XML de um feed em uma lista de ``FeedEntry``."""
    # Remove BOM e declarações problemáticas
    payload = xml_text.lstrip("\ufeff").strip()
    if not payload:
        return []

    # Feeds vêm de portais conhecidos e são parseados sem resolução de
    # entidades externas (ElementTree não expande DTDs por padrão).
    try:
        root = ET.fromstring(payload)  # noqa: S314
    except ET.ParseError:
        # Alguns feeds têm caracteres de controle inválidos
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", payload)
        try:
            root = ET.fromstring(sanitized)  # noqa: S314
        except ET.ParseError:
            return []

    entries: list[FeedEntry] = []

    # RSS 2.0
    for item in root.iter("item"):
        link = _text(item.find("link"))
        if not link:
            guid = item.find("guid")
            if guid is not None and guid.attrib.get("isPermaLink", "true") != "false":
                link = _text(guid)
        if not link:
            continue

        description = _text(item.find("description"))
        content_encoded = _text(item.find("content:encoded", _NAMESPACES))
        summary_source = content_encoded or description

        categories = tuple(value for node in item.findall("category") if (value := _text(node)))
        author = _text(item.find("dc:creator", _NAMESPACES)) or _text(item.find("author"))

        image = None
        media = item.find("media:content", _NAMESPACES)
        if media is not None:
            image = clean_text(media.attrib.get("url"))
        if image is None:
            image = _first_image(description) or _first_image(content_encoded)

        entries.append(
            FeedEntry(
                url=link,
                title=_text(item.find("title")),
                summary=html_to_text(summary_source),
                author=author,
                published_at=parse_datetime(_text(item.find("pubDate"))),
                categories=categories,
                image_url=image,
            )
        )

    if entries:
        return entries

    # Atom
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        link_node = entry.find("atom:link[@rel='alternate']", _NAMESPACES)
        if link_node is None:
            link_node = entry.find("atom:link", _NAMESPACES)
        link = clean_text(link_node.attrib.get("href")) if link_node is not None else None
        if not link:
            continue

        summary_node = entry.find("atom:summary", _NAMESPACES)
        content_node = entry.find("atom:content", _NAMESPACES)
        summary_html = _text(content_node) or _text(summary_node)

        entries.append(
            FeedEntry(
                url=link,
                title=_text(entry.find("atom:title", _NAMESPACES)),
                summary=html_to_text(summary_html),
                author=_text(entry.find("atom:author/atom:name", _NAMESPACES)),
                published_at=parse_datetime(
                    _text(entry.find("atom:published", _NAMESPACES))
                    or _text(entry.find("atom:updated", _NAMESPACES))
                ),
                categories=tuple(
                    value
                    for node in entry.findall("atom:category", _NAMESPACES)
                    if (value := clean_text(node.attrib.get("term")))
                ),
                image_url=_first_image(summary_html),
            )
        )

    return entries
