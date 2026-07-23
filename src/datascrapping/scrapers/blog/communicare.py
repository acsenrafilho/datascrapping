from __future__ import annotations

from urllib.parse import urljoin, urlparse

from datascrapping.core.registry import register
from datascrapping.scrapers.blog.base_blog import BlogScraper


def classify_communicare(url_base: str, link_href: str) -> tuple[bool, str]:
    domain = urlparse(url_base).netloc
    link = urljoin(url_base, link_href)
    parsed = urlparse(link)
    path = parsed.path.lower().strip("/")
    lower = link.lower()

    if domain not in parsed.netloc:
        return False, "dominio_externo"
    if not path or "#" in link:
        return False, "vazio_ou_ancora"

    blocked = (
        "blog/page/",
        "/page/",
        "/pagina/",
        "/tag/",
        "/category/",
        "/categoria/",
        "/author/",
        "/autor/",
        "?s=",
        "wp-content",
        "wp-json",
        "/feed",
        "/contato",
        "/carreiras",
        "/politica",
    )
    if any(item in lower for item in blocked):
        return False, "rota_bloqueada"

    parts = [part for part in path.split("/") if part]
    if not parts:
        return False, "sem_path"

    if parts[0] == "blog" and len(parts) >= 2:
        if parts[1] == "page":
            return False, "paginacao_blog"
        return True, "ok_blog_slug"

    institutional = {
        "contato",
        "carreiras",
        "quem-somos",
        "depoimentos",
        "atendimento-remoto",
        "zumbido",
        "nossas-unidades",
        "aparelhos-auditivos",
        "parceiros",
    }
    if parts[0] in institutional:
        return False, "pagina_institucional"
    return False, "fora_do_padrao_blog"


@register
class CommunicareBlogScraper(BlogScraper):
    name = "blog.communicare"
    description = "Collect Communicare blog articles as Markdown"
    listing_url = "https://comunicareaparelhosauditivos.com/blog/"
    output_subdir = "communicare"
    pagination_mode = "numbered"
    classify_fn = staticmethod(classify_communicare)
