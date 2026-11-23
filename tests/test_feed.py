"""Testes do parser de feeds."""

from __future__ import annotations

from campinas_news.scraping.feed import parse_feed

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>CBN Campinas</title>
    <item>
      <title>Ponte Preta negocia permanência</title>
      <link>https://cbncampinas.com.br/2026/11/ponte-preta/</link>
      <dc:creator><![CDATA[Antônio Luppi]]></dc:creator>
      <pubDate>Mon, 23 Nov 2026 13:51:17 +0000</pubDate>
      <category><![CDATA[Esporte]]></category>
      <category><![CDATA[Ponte Preta]]></category>
      <description><![CDATA[<p>O zagueiro Gabriel Caran...</p>]]></description>
      <content:encoded><![CDATA[<p>Texto completo</p><img src="https://x.test/a.jpg">]]></content:encoded>
      <media:content url="https://x.test/media.jpg" medium="image"/>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Exemplo</title>
  <entry>
    <title>Matéria Atom</title>
    <link rel="alternate" href="https://exemplo.test/materia"/>
    <published>2026-11-23T10:00:00-03:00</published>
    <summary>Resumo da matéria</summary>
    <author><name>Redação</name></author>
    <category term="Cidades"/>
  </entry>
</feed>
"""


def test_parse_rss_extracts_fields() -> None:
    entries = parse_feed(RSS_SAMPLE)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.url == "https://cbncampinas.com.br/2026/11/ponte-preta/"
    assert entry.title == "Ponte Preta negocia permanência"
    assert entry.author == "Antônio Luppi"
    assert entry.categories == ("Esporte", "Ponte Preta")
    assert entry.published_at is not None
    assert entry.published_at.isoformat() == "2026-11-23T13:51:17+00:00"
    assert entry.summary == "Texto completo"
    assert entry.image_url == "https://x.test/media.jpg"


def test_parse_atom_extracts_fields() -> None:
    entries = parse_feed(ATOM_SAMPLE)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.url == "https://exemplo.test/materia"
    assert entry.title == "Matéria Atom"
    assert entry.author == "Redação"
    assert entry.categories == ("Cidades",)
    assert entry.published_at is not None
    assert entry.published_at.isoformat() == "2026-11-23T13:00:00+00:00"


def test_parse_feed_handles_bom_and_invalid_xml() -> None:
    assert parse_feed("\ufeff" + RSS_SAMPLE)
    assert parse_feed("isto não é xml") == []
    assert parse_feed("") == []


def test_parse_feed_skips_items_without_link() -> None:
    xml = """<rss version="2.0"><channel><item><title>sem link</title></item></channel></rss>"""
    assert parse_feed(xml) == []
