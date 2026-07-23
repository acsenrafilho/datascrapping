from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from datascrapping.core.registry import register
from datascrapping.scrapers.blog.base_blog import BlogScraper


def classify_sonorita(url_base: str, link_href: str) -> tuple[bool, str]:
    link = urljoin(url_base, link_href)
    parsed = urlparse(link)
    domain = urlparse(url_base).netloc
    path = parsed.path.lower().strip("/")
    lower = link.lower()

    if domain not in parsed.netloc:
        return False, "dominio_externo"
    if not path or "#" in link:
        return False, "vazio_ou_ancora"

    blocked = (
        "/page/",
        "?s=",
        "wp-content",
        "wp-json",
        "/feed",
        "/faq",
        "/contato",
        "/convenios",
        "/a-sonorita",
        "/aparelhos-auditivos",
        "/politica-de-privacidade",
    )
    if any(item in lower for item in blocked):
        return False, "rota_bloqueada"

    if "sonoritaaparelhosauditivos.com.br" not in parsed.netloc:
        return False, "dominio_invalido"

    institutional = {
        "home",
        "blog",
        "blog-saude-auditiva",
        "contato",
        "faq",
        "convenios",
        "a-sonorita",
        "agendar-avaliacao",
    }
    if path in institutional:
        return False, "pagina_institucional"

    return True, "ok"


@register
class SonoritaBlogScraper(BlogScraper):
    name = "blog.sonorita"
    description = "Collect Sonorita blog articles as Markdown"
    listing_url = (
        "https://sonoritaaparelhosauditivos.com.br/blog-saude-auditiva"
    )
    output_subdir = "sonorita"
    pagination_mode = "bfs"
    max_listing_pages = 300
    classify_fn = staticmethod(classify_sonorita)

    def _is_pagination_link(self, link: str, anchor_text: str) -> bool:
        lower = link.lower()
        if re.search(r"/blog-saude-auditiva/?\d+/?$", lower):
            return True
        return super()._is_pagination_link(link, anchor_text)
