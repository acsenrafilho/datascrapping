"""Fixtures and unit tests for places.website crawl helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from datascrapping.scrapers.places.crawl import (
    WebsiteCrawler,
    extract_text_from_html,
    normalize_url,
)

SAMPLE_HOMEPAGE = """
<html><head><title>Clinica Exemplo</title></head>
<body>
<nav>
  <a href="/sobre">Sobre</a>
  <a href="/contato">Contato</a>
  <a href="/blog/post-1">Blog</a>
</nav>
<p>Telefone (19) 99999-8888</p>
</body></html>
"""

SAMPLE_ABOUT = """
<html><body>
<p>CNPJ 11.444.777/0001-61</p>
<p>contato@clinicaexemplo.com.br</p>
<a href="mailto:vendas@clinicaexemplo.com.br">E-mail</a>
</body></html>
"""

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://clinicaexemplo.com.br/sobre</loc></url>
  <url><loc>https://clinicaexemplo.com.br/contato</loc></url>
  <url><loc>https://clinicaexemplo.com.br/blog/noticia-1</loc></url>
</urlset>
"""


def test_normalize_url_adds_https():
    assert normalize_url("clinicaexemplo.com.br") == "https://clinicaexemplo.com.br"
    assert normalize_url("http://x.com") == "http://x.com"


def test_normalize_url_rejects_invalid():
    try:
        normalize_url("not a url")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_extract_text_strips_scripts():
    html = "<html><script>evil()</script><p>CNPJ 11.444.777/0001-61</p></html>"
    text = extract_text_from_html(html)
    assert "evil" not in text
    assert "11.444.777" in text


def test_robots_disallow(monkeypatch):
    crawler = WebsiteCrawler()
    rp = MagicMock()
    rp.can_fetch.return_value = False

    with patch(
        "datascrapping.scrapers.places.crawl.RobotFileParser",
        return_value=rp,
    ):
        # read() is called on the instance
        assert crawler.check_robots_txt("https://example.com") is False


def test_robots_missing_allows():
    crawler = WebsiteCrawler()
    rp = MagicMock()
    rp.read.side_effect = OSError("missing")
    with patch(
        "datascrapping.scrapers.places.crawl.RobotFileParser",
        return_value=rp,
    ):
        assert crawler.check_robots_txt("https://example.com") is True


def test_filter_main_pages_excludes_blog():
    crawler = WebsiteCrawler()
    urls = [
        "https://x.com/sobre",
        "https://x.com/blog/post-1",
        "https://x.com/contato",
    ]
    filtered = crawler.filter_main_pages(urls)
    assert "https://x.com/blog/post-1" not in filtered
    assert filtered[0] in ("https://x.com/sobre", "https://x.com/contato")


def test_discover_from_homepage():
    crawler = WebsiteCrawler()
    with patch.object(crawler, "fetch_page_content", return_value=SAMPLE_HOMEPAGE):
        links = crawler.discover_pages_from_homepage("https://clinicaexemplo.com.br")
    assert any(u.endswith("/sobre") for u in links)
    assert any(u.endswith("/contato") for u in links)


def test_discover_from_sitemap():
    crawler = WebsiteCrawler()
    response = MagicMock()
    response.status_code = 200
    response.content = SAMPLE_SITEMAP.encode()
    with patch(
        "datascrapping.scrapers.places.crawl.requests.get",
        return_value=response,
    ):
        urls = crawler.discover_pages_from_sitemap("https://clinicaexemplo.com.br")
    assert any("/sobre" in u for u in urls)
    assert not any("/blog/" in u for u in urls)


def test_common_paths_include_contato():
    crawler = WebsiteCrawler()
    paths = crawler.discover_pages_common_paths("https://clinicaexemplo.com.br")
    assert any(p.rstrip("/").endswith("/contato") for p in paths)


def test_fetch_page_increments_stats():
    crawler = WebsiteCrawler()
    ok = MagicMock(status_code=200, text=SAMPLE_HOMEPAGE)
    bad = MagicMock(status_code=404, text="")
    with patch(
        "datascrapping.scrapers.places.crawl.requests.get",
        side_effect=[ok, bad],
    ):
        assert crawler.fetch_page_content("https://x.com/") is not None
        assert crawler.fetch_page_content("https://x.com/missing") is None
    assert crawler.stats.pages_fetched == 1
    assert crawler.stats.pages_failed == 1


def test_crawl_robots_disallowed():
    crawler = WebsiteCrawler()
    with patch.object(crawler, "check_robots_txt", return_value=False):
        result = crawler.crawl("https://clinicaexemplo.com.br", polite=False)
    assert result.status == "completed"
    assert "robots" in result.status_reason.lower()
    assert result.pages == {}
