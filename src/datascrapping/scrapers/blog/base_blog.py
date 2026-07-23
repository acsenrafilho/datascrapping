from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.http import HttpClient
from datascrapping.core.sinks import MarkdownSink

logger = logging.getLogger(__name__)

ClassifyFn = Callable[[str, str], tuple[bool, str]]

BLOCKED_PATH_FRAGMENTS = (
    "wp-content",
    "wp-json",
    "/feed",
    "/tag/",
    "/tags/",
    "/category/",
    "/categoria/",
    "/author/",
    "/autor/",
    "/page/",
    "/pagina/",
    "?s=",
    "/contato",
    "/contact",
    "/about",
    "/sobre",
    "/carreiras",
    "/careers",
    "/politica",
    "/privacy",
    "/login",
    "/cart",
    "/checkout",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".zip",
)

INSTITUTIONAL_SLUGS = {
    "home",
    "blog",
    "artigos",
    "news",
    "noticias",
    "contato",
    "contact",
    "sobre",
    "about",
    "quem-somos",
    "servicos",
    "services",
    "produtos",
    "products",
    "equipe",
    "team",
    "faq",
    "login",
    "carrinho",
}


def default_classify_article_link(url_base: str, link_href: str) -> tuple[bool, str]:
    """Improved generic classifier for unknown blog layouts."""
    domain = urlparse(url_base).netloc
    link = urljoin(url_base, link_href)
    parsed = urlparse(link)
    base_parsed = urlparse(url_base)
    path = parsed.path.lower().strip("/")
    lower = link.lower()

    if domain not in parsed.netloc:
        return False, "dominio_externo"
    if not path or "#" in link:
        return False, "vazio_ou_ancora"
    if link.rstrip("/") == url_base.rstrip("/"):
        return False, "mesma_listagem"
    if any(item in lower for item in BLOCKED_PATH_FRAGMENTS):
        return False, "rota_bloqueada"
    if re.search(r"/page/\d+/?$", lower) or re.search(r"/pagina/\d+/?$", lower):
        return False, "paginacao"
    if re.search(r"^\d{4}/\d{2}/?$", path):
        return False, "arquivo_mensal"

    parts = [part for part in path.split("/") if part]
    if not parts:
        return False, "sem_path"
    if parts[0] in INSTITUTIONAL_SLUGS and len(parts) == 1:
        return False, "pagina_institucional"

    base_parts = [part for part in base_parsed.path.lower().strip("/").split("/") if part]

    # /blog/<slug>/ or /artigos/<slug>/
    if len(parts) >= 2 and parts[0] in {
        "blog",
        "artigos",
        "news",
        "noticias",
        "posts",
    }:
        if parts[1] == "page":
            return False, "paginacao_blog"
        return True, "ok_blog_slug"

    # Listing is under /blog/ and post is a single root slug
    if base_parts and base_parts[0] in {"blog", "artigos", "news"} and len(parts) == 1:
        if parts[0] in INSTITUTIONAL_SLUGS:
            return False, "pagina_institucional"
        return True, "ok_slug_raiz"

    # Generic: multi-segment non-institutional paths look like posts
    if len(parts) >= 2 and parts[0] not in INSTITUTIONAL_SLUGS:
        return True, "ok_path"
    if len(parts) == 1 and parts[0] not in INSTITUTIONAL_SLUGS:
        return True, "ok_slug"

    return False, "nao_classificado"


def detect_pagination_mode(html: str, listing_url: str) -> str:
    """Return numbered, bfs, or simple from listing HTML heuristics."""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    if re.search(r"Página\s+\d+\s+de\s+\d+", text, flags=re.IGNORECASE):
        return "numbered"
    if re.search(r"/page/\d+", html, flags=re.IGNORECASE) or re.search(
        r"/pagina/\d+", html, flags=re.IGNORECASE
    ):
        return "numbered"
    if re.search(r"[?&]paged=\d+", html, flags=re.IGNORECASE):
        return "bfs"
    lower = html.lower()
    if "next" in lower or "próximo" in lower or "proximo" in lower:
        return "bfs"
    return "simple"


class BlogScraper(BaseScraper):
    """Reusable blog crawler: discover listing pages, collect posts, save MD."""

    name = "blog.base"
    description = "Base blog scraper"
    listing_url: str = ""
    output_subdir: str = "blog"
    min_content_length: int = 200
    max_listing_pages: int = 300
    classify_fn: ClassifyFn = default_classify_article_link
    pagination_mode: str = "simple"  # simple | numbered | bfs | auto

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        listing_url = ctx.extras.get("url") or self.listing_url
        if not listing_url:
            raise ValueError(f"{self.name} requires a listing URL")

        if ctx.extras.get("pagination"):
            self.pagination_mode = str(ctx.extras["pagination"])
        if ctx.extras.get("max_pages"):
            self.max_listing_pages = int(ctx.extras["max_pages"])

        subdir = ctx.extras.get("out") or self.output_subdir
        target = Path(ctx.out_dir) / subdir
        client = HttpClient(delay_min=ctx.delay_min, delay_max=ctx.delay_max)
        sink = MarkdownSink(target)

        logger.info("--- Starting crawl: %s ---", listing_url)
        try:
            links = self.collect_article_links(client, listing_url)
            logger.info("Candidate article links: %s", len(links))

            saved = skipped = errors = 0
            for index, link in enumerate(links, start=1):
                logger.info("[EXTRACT] %s/%s %s", index, len(links), link)
                try:
                    title, markdown = self.extract_article(client, link)
                except Exception:
                    logger.exception("Failed to extract %s", link)
                    errors += 1
                    continue

                if (
                    title
                    and markdown
                    and len(markdown) > self.min_content_length
                ):
                    path = sink.write(
                        title, link, markdown, dry_run=ctx.dry_run
                    )
                    saved += 1
                    logger.info("[EXTRACT] Saved: %s", path.name)
                else:
                    skipped += 1
                    logger.info("[EXTRACT] Skipped (short/empty)")
        finally:
            client.close()

        return ScrapeResult(
            scraper=self.name,
            saved=saved,
            skipped=skipped,
            errors=errors,
            output_path=target,
            message=f"Saved {saved}, skipped {skipped}, errors {errors}",
        )

    def collect_article_links(
        self, client: HttpClient, listing_url: str
    ) -> list[str]:
        pages = self.discover_listing_pages(client, listing_url)
        logger.info("Listing pages detected: %s", len(pages))
        found: set[str] = set()

        for page in pages:
            logger.info("[LISTING] Collecting links on: %s", page)
            try:
                response = client.get(page)
            except Exception:
                logger.exception("Failed to open listing page %s", page)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            containers = self._post_containers(soup)
            candidates = accepted = 0
            rejections: dict[str, int] = {}

            for container in containers:
                for anchor in container.find_all("a", href=True):
                    candidates += 1
                    url = urljoin(page, anchor["href"])
                    ok, reason = self.classify_fn(listing_url, url)
                    if ok:
                        found.add(url)
                        accepted += 1
                    else:
                        rejections[reason] = rejections.get(reason, 0) + 1

            logger.info(
                "[COLLECT] page=%s candidates=%s accepted=%s unique=%s",
                page,
                candidates,
                accepted,
                len(found),
            )
            if rejections:
                logger.debug("[COLLECT] rejections=%s", rejections)

        return sorted(found)

    def discover_listing_pages(
        self, client: HttpClient, listing_url: str
    ) -> list[str]:
        mode = self.pagination_mode
        if mode == "auto":
            mode = self._resolve_auto_mode(client, listing_url)
            logger.info("Auto pagination resolved to: %s", mode)

        if mode == "numbered":
            pages = self._discover_numbered_pages(client, listing_url)
            return pages[: self.max_listing_pages]
        if mode == "bfs":
            return self._discover_bfs_pages(client, listing_url)
        return [listing_url]

    def _resolve_auto_mode(self, client: HttpClient, listing_url: str) -> str:
        try:
            response = client.get(listing_url)
        except Exception:
            logger.exception("Auto mode failed to open %s", listing_url)
            return "simple"
        return detect_pagination_mode(response.text, listing_url)

    def _discover_numbered_pages(
        self, client: HttpClient, listing_url: str
    ) -> list[str]:
        pages = {listing_url}
        try:
            response = client.get(listing_url)
        except Exception:
            logger.exception("Failed to open listing root %s", listing_url)
            return [listing_url]

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        match = re.search(
            r"Página\s+\d+\s+de\s+(\d+)", text, flags=re.IGNORECASE
        )
        if match:
            total = int(match.group(1))
            base = listing_url.rstrip("/") + "/"
            for number in range(2, total + 1):
                pages.add(urljoin(base, f"page/{number}/"))

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if re.search(r"/page/\d+/?$", href) or re.search(
                r"/pagina/\d+/?$", href
            ):
                pages.add(urljoin(listing_url, href))

        return sorted(pages)

    def _discover_bfs_pages(
        self, client: HttpClient, listing_url: str
    ) -> list[str]:
        domain = urlparse(listing_url).netloc
        visited: set[str] = set()
        queue = [listing_url]
        listing_pages: set[str] = set()

        while queue and len(visited) < self.max_listing_pages:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            logger.info(
                "[LISTING] Exploring: %s (visited=%s queue=%s)",
                current,
                len(visited),
                len(queue),
            )
            try:
                response = client.get(current)
            except Exception:
                logger.exception("Failed listing page %s", current)
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            listing_pages.add(current)

            for anchor in soup.find_all("a", href=True):
                text = anchor.get_text(" ", strip=True).lower()
                link = urljoin(current, anchor["href"])
                if urlparse(link).netloc != domain:
                    continue
                if self._is_pagination_link(link, text):
                    if link not in visited and link not in queue:
                        queue.append(link)

        return sorted(listing_pages)

    def _is_pagination_link(self, link: str, anchor_text: str) -> bool:
        lower = link.lower()
        return bool(
            re.search(r"/page/\d+/?$", lower)
            or re.search(r"/pagina/\d+/?$", lower)
            or re.search(r"[?&]paged=\d+", lower)
            or "posts-antigos" in lower
            or "proximo" in anchor_text
            or "next" in anchor_text
            or "previous" in anchor_text
        )

    def _post_containers(self, soup: BeautifulSoup) -> list:
        containers = []
        for article in soup.find_all("article"):
            classes = article.get("class") or []
            if any(cls == "type-post" for cls in classes):
                containers.append(article)
        if containers:
            return containers
        return soup.find_all(["article", "h1", "h2", "h3", "main", "section"])

    def extract_article(
        self, client: HttpClient, url: str
    ) -> tuple[str | None, str | None]:
        response = client.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else "Sem Titulo"

        for tag in soup(
            ["nav", "footer", "header", "aside", "script", "style", "form"]
        ):
            tag.decompose()

        best = None
        max_paragraphs = 0
        for block in soup.find_all(["div", "article", "main", "section"]):
            count = len(block.find_all("p"))
            if count > max_paragraphs:
                max_paragraphs = count
                best = block

        if not best:
            return title, "Não foi possível extrair o conteúdo automaticamente."

        return title, md(str(best), heading_style="ATX")
