from __future__ import annotations

from urllib.parse import urljoin, urlparse

from datascrapping.core.registry import register
from datascrapping.scrapers.blog.base_blog import BlogScraper


def classify_auditik(url_base: str, link_href: str) -> tuple[bool, str]:
    domain = urlparse(url_base).netloc
    href = link_href
    if href.startswith("/"):
        href = urljoin(url_base, href)
    if any(
        item in href
        for item in (
            "wp-content",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
            "/category/",
            "?et_blog",
            "/artigos/page",
        )
    ):
        return False, "rota_bloqueada"
    parsed = urlparse(href)
    if parsed.netloc != domain or href.rstrip("/") == url_base.rstrip("/"):
        return False, "dominio_ou_raiz"
    return True, "ok"


@register
class AuditikBlogScraper(BlogScraper):
    name = "blog.auditik"
    description = "Collect Auditik blog articles as Markdown"
    listing_url = "https://auditik.com.br/artigos/"
    output_subdir = "auditik"
    pagination_mode = "numbered"
    classify_fn = staticmethod(classify_auditik)
