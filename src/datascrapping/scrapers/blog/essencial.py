from __future__ import annotations

from urllib.parse import urljoin, urlparse

from datascrapping.core.registry import register
from datascrapping.scrapers.blog.base_blog import BlogScraper


def classify_essencial(url_base: str, link_href: str) -> tuple[bool, str]:
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
        "/blog/page/",
        "/blog/pagina/",
        "/blog/",
        "/autor/",
        "/tag/",
        "/category/",
        "/categoria/",
        "/author/",
        "?s=",
        "wp-content",
        "wp-json",
        "/feed",
        "/glossario",
    )
    if any(item in lower for item in blocked):
        return False, "rota_bloqueada"

    if "essencialaparelhosauditivos.com" not in parsed.netloc:
        return False, "dominio_invalido"

    institutional = {
        "home",
        "blog",
        "sobre",
        "contato",
        "unidades",
        "modelos",
        "marcas",
        "tipos-de-aparelhos",
        "equipe-profissional",
        "trabalhe-conosco",
        "profissionais",
        "saude-auditiva",
        "cidades",
        "tipos",
        "web-stories",
    }
    if path in institutional:
        return False, "pagina_institucional"

    parts = [part for part in path.split("/") if part]
    if not parts:
        return False, "sem_path"
    if len(parts) == 1:
        return True, "ok_slug_raiz"

    blocked_prefix = ("blog", "autor", "glossario", "categoria", "tag", "wp-")
    if parts[0] in blocked_prefix:
        return False, "prefixo_bloqueado"
    if len(parts) >= 2:
        return True, "ok"
    return False, "nao_classificado"


@register
class EssencialBlogScraper(BlogScraper):
    name = "blog.essencial"
    description = "Collect Essencial AASI blog articles as Markdown"
    listing_url = "https://www.essencialaparelhosauditivos.com/blog/"
    output_subdir = "essencial_aasi"
    pagination_mode = "bfs"
    max_listing_pages = 200
    classify_fn = staticmethod(classify_essencial)
