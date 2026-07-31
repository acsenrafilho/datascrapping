"""Tests for best-effort social profile enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock

from datascrapping.scrapers.places.social_enrich import (
    enrich_from_social_urls,
    fetch_social_html,
)


def test_fetch_social_html_ok():
    response = MagicMock()
    response.status_code = 200
    response.text = "<html><body>ok</body></html>"

    def fake_get(*_a, **_k):
        return response

    html, status = fetch_social_html(
        "https://instagram.com/x", http_get=fake_get
    )
    assert status == "ok"
    assert html and "ok" in html


def test_fetch_social_html_blocked():
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden"

    html, status = fetch_social_html(
        "https://instagram.com/x", http_get=lambda *_a, **_k: response
    )
    assert html is None
    assert status == "blocked"


def test_enrich_from_social_urls_extracts_contacts():
    html = """
    <html><head>
      <meta property="og:description" content="Fale: contato@loja.com / wa.me/5516999000111" />
    </head><body></body></html>
    """
    response = MagicMock()
    response.status_code = 200
    response.text = html

    result = enrich_from_social_urls(
        {"instagram": "https://instagram.com/loja", "facebook": ""},
        http_get=lambda *_a, **_k: response,
        sleep_fn=lambda _: None,
        polite=True,
    )
    assert "instagram:ok" in result.status
    assert "contato@loja.com" in result.emails
    assert result.whatsapp == "5516999000111"


def test_enrich_login_wall_without_contact():
    html = """
    <html><head><title>Log in</title>
    <meta property="og:description" content="Log in" />
    </head><body>Log in Sign in password create an account</body></html>
    """
    response = MagicMock()
    response.status_code = 200
    response.text = html

    result = enrich_from_social_urls(
        {"linkedin": "https://linkedin.com/company/x"},
        http_get=lambda *_a, **_k: response,
        sleep_fn=lambda _: None,
    )
    assert "linkedin:blocked" in result.status
    assert not result.emails
