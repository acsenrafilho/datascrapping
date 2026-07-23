from datascrapping.scrapers.blog.base_blog import (
    default_classify_article_link,
    detect_pagination_mode,
)


def test_generic_accepts_blog_slug():
    ok, reason = default_classify_article_link(
        "https://example.com/blog/",
        "https://example.com/blog/perda-auditiva/",
    )
    assert ok is True
    assert reason == "ok_blog_slug"


def test_generic_rejects_contact_and_pagination():
    ok, _ = default_classify_article_link(
        "https://example.com/blog/",
        "https://example.com/contato/",
    )
    assert ok is False
    ok, reason = default_classify_article_link(
        "https://example.com/blog/",
        "https://example.com/blog/page/2/",
    )
    assert ok is False
    assert reason in {"rota_bloqueada", "paginacao", "paginacao_blog"}


def test_generic_accepts_root_slug_when_listing_is_blog():
    ok, reason = default_classify_article_link(
        "https://example.com/blog/",
        "https://example.com/aparelho-auditivo/",
    )
    assert ok is True
    assert reason == "ok_slug_raiz"


def test_detect_pagination_numbered_from_text():
    html = "<html><body>Página 1 de 12</body></html>"
    assert detect_pagination_mode(html, "https://x/blog/") == "numbered"


def test_detect_pagination_bfs_from_next():
    html = '<html><body><a href="/blog/page/2/">Next</a></body></html>'
    assert detect_pagination_mode(html, "https://x/blog/") in {
        "numbered",
        "bfs",
    }


def test_detect_pagination_simple():
    html = "<html><body><h1>Blog</h1><p>Only one page</p></body></html>"
    assert detect_pagination_mode(html, "https://x/blog/") == "simple"
