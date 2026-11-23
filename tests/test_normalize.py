"""Testes das funções puras de normalização."""

from __future__ import annotations

import pytest

from campinas_news.scraping.normalize import (
    canonicalize_url,
    clean_text,
    content_hash,
    count_words,
    html_to_text,
    sanitize_body_html,
    slugify,
    url_hash,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Olá\u00a0  mundo \u200b", "Olá mundo"),
        ("<b>não</b>", "<b>não</b>"),
        ("a\n\nb", "a b"),
        ("", None),
        (None, None),
    ],
)
def test_clean_text(raw: str | None, expected: str | None) -> None:
    assert clean_text(raw) == expected


def test_clean_text_unescapes_entities() -> None:
    assert clean_text("Campinas & Região") == "Campinas & Região"


def test_slugify() -> None:
    assert slugify("Ciclista morre após acidente em Jaguariúna") == (
        "ciclista-morre-apos-acidente-em-jaguariuna"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://www.acidadeon.com/campinas/cotidiano/materia/?utm_source=x&utm_medium=y",
            "https://acidadeon.com/campinas/cotidiano/materia",
        ),
        ("https://G1.globo.com/sp/campinas-regiao/#top", "https://g1.globo.com/sp/campinas-regiao"),
        (
            "https://sampi.net.br/campinas/noticias/1/a/2026/11/b?fbclid=abc",
            "https://sampi.net.br/campinas/noticias/1/a/2026/11/b",
        ),
        ("https://horacampinas.com.br/post/", "https://horacampinas.com.br/post"),
    ],
)
def test_canonicalize_url(url: str, expected: str) -> None:
    assert canonicalize_url(url) == expected


def test_canonicalize_url_is_idempotent() -> None:
    once = canonicalize_url("https://www.g1.globo.com/x/?utm_source=a")
    assert canonicalize_url(once) == once


def test_url_hash_stable_across_tracking_params() -> None:
    a = url_hash("https://g1.globo.com/noticia/1/x.ghtml?utm_source=twitter")
    b = url_hash("https://www.g1.globo.com/noticia/1/x.ghtml")
    assert a == b


def test_content_hash_changes_with_body() -> None:
    base = content_hash("Título", "corpo")
    assert base != content_hash("Título", "corpo editado")
    assert base == content_hash("Título", "corpo")


def test_count_words() -> None:
    assert count_words("Uma mulher de 59 anos ficou ferida.") == 7
    assert count_words(None) == 0


def test_html_to_text_strips_boilerplate() -> None:
    fragment = """
    <div class="texto0">
      <p>Primeiro parágrafo da matéria.</p>
      <div class="publicidade">Anúncio</div>
      <p>Segundo parágrafo.</p>
      <script>alert(1)</script>
    </div>
    """
    text = html_to_text(fragment)
    assert text is not None
    assert "Primeiro parágrafo" in text
    assert "Segundo parágrafo" in text
    assert "Anúncio" not in text
    assert "alert" not in text


def test_html_to_text_dedupes_consecutive_paragraphs() -> None:
    fragment = "<p>Igual</p><p>Igual</p><p>Diferente</p>"
    assert html_to_text(fragment) == "Igual\n\nDiferente"


def test_sanitize_body_html_removes_scripts() -> None:
    result = sanitize_body_html("<p>ok</p><script>bad()</script>")
    assert result is not None
    assert "ok" in result
    assert "bad" not in result
