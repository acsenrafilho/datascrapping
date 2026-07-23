from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from datascrapping.core.registry import register
from datascrapping.scrapers.blog.base_blog import BlogScraper


def classify_otoclinic(url_base: str, link_href: str) -> tuple[bool, str]:
    link = urljoin(url_base, link_href)
    parsed = urlparse(link)
    domain = urlparse(url_base).netloc
    path = parsed.path.strip("/")
    path_lower = path.lower()
    lower = link.lower()

    if parsed.netloc != domain:
        return False, "dominio_externo"
    if not path or "#" in link:
        return False, "vazio_ou_ancora"

    blocked = (
        "/wp-content/",
        "/wp-json/",
        "/feed/",
        "/comments/",
        "?s=",
        "/tag/",
        "/category/",
        "/author/",
        "/contato",
        "/empresa",
        "/produtos",
        "/acessorios",
        "/servicos",
        "/localizacao",
    )
    if any(item in lower for item in blocked):
        return False, "rota_bloqueada"

    if path_lower in {"blog-otoclinic", "blog"}:
        return False, "pagina_blog"
    if re.search(r"^\d{4}/\d{2}/?$", path_lower):
        return False, "arquivo_mensal"
    if re.search(r"^page/\d+/?$", path_lower):
        return False, "paginacao"

    parts = [part for part in path_lower.split("/") if part]
    if len(parts) == 1:
        return True, "ok_slug_raiz"
    return False, "fora_do_padrao"


@register
class OtoclinicBlogScraper(BlogScraper):
    name = "blog.otoclinic"
    description = "Collect Otoclinic blog articles as Markdown"
    listing_url = "https://otoclinic.com.br/blog-otoclinic/"
    output_subdir = "otoclinic"
    pagination_mode = "bfs"
    max_listing_pages = 600
    classify_fn = staticmethod(classify_otoclinic)

    def _is_pagination_link(self, link: str, anchor_text: str) -> bool:
        path = urlparse(link).path.lower().strip("/")
        if path in {"blog-otoclinic", "blog"}:
            return True
        if re.search(r"^\d{4}/\d{2}/?$", path):
            return True
        return super()._is_pagination_link(link, anchor_text)
