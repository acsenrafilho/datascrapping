"""HTTP crawl helpers for places.website (ported from backend website_scrapper)."""

from __future__ import annotations

import logging
import random
import re
import time
import warnings
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

logger = logging.getLogger(__name__)

MAX_PAGES_PER_SITE = 15
REQUEST_TIMEOUT = 10
USER_AGENT = "AurisBot/1.0 (+https://auris.com.br/bot)"
MIN_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 3

PRIORITY_KEYWORDS = (
    "about",
    "sobre",
    "quem-somos",
    "contact",
    "contato",
    "fale-conosco",
    "service",
    "servico",
    "servicos",
    "product",
    "produto",
    "produtos",
    "empresa",
    "company",
    "historia",
)

EXCLUDE_PATTERNS = (
    r"/blog/",
    r"/news/",
    r"/noticia/",
    r"/artigo/",
    r"/page/\d+",
    r"/p/\d+",
    r"/\d{4}/\d{2}/",
    r"/category/",
    r"/tag/",
    r"/author/",
    r"\?",
    r"#",
)

COMMON_PATHS = (
    "/",
    "/index.html",
    "/index.php",
    "/sobre",
    "/sobre-nos",
    "/quem-somos",
    "/about",
    "/about-us",
    "/contato",
    "/fale-conosco",
    "/contact",
    "/produtos",
    "/products",
    "/servicos",
    "/services",
    "/ofertas",
    "/offers",
    "/empresa",
    "/company",
)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url or " " in url:
        raise ValueError(f"Invalid URL format: {url}")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL format: {url}")
    return url


def extract_text_from_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(chunk for chunk in chunks if chunk)
    except Exception as exc:
        logger.error("Error extracting text from HTML: %s", exc)
        return ""


@dataclass
class CrawlStats:
    pages_fetched: int = 0
    pages_failed: int = 0


@dataclass
class CrawlResult:
    pages: dict[str, str] = field(default_factory=dict)
    stats: CrawlStats = field(default_factory=CrawlStats)
    status: str = "completed"
    status_reason: str = ""
    base_url: str = ""


class WebsiteCrawler:
    """Discover and fetch main pages from a company website."""

    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        self.timeout = timeout
        self.stats = CrawlStats()

    def check_robots_txt(self, base_url: str) -> bool:
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
            except Exception as read_error:
                logger.warning(
                    "Could not read robots.txt from %s: %s",
                    robots_url,
                    read_error,
                )
                return True
            can_fetch = rp.can_fetch(USER_AGENT, base_url)
            logger.info(
                "robots.txt check for %s: %s",
                base_url,
                "allowed" if can_fetch else "disallowed",
            )
            return can_fetch
        except Exception as exc:
            logger.warning("Failed to check robots.txt for %s: %s", base_url, exc)
            return True

    def fetch_page_content(self, url: str) -> Optional[str]:
        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
                verify=True,
            )
            if response.status_code == 200:
                self.stats.pages_fetched += 1
                return response.text
            logger.warning("Failed to fetch %s: HTTP %s", url, response.status_code)
            self.stats.pages_failed += 1
            return None
        except requests.exceptions.Timeout:
            logger.warning("Timeout fetching %s", url)
            self.stats.pages_failed += 1
            return None
        except requests.exceptions.RequestException as exc:
            logger.warning("Request error fetching %s: %s", url, exc)
            self.stats.pages_failed += 1
            return None
        except Exception as exc:
            logger.error("Unexpected error fetching %s: %s", url, exc)
            self.stats.pages_failed += 1
            return None

    def filter_main_pages(self, urls: list[str]) -> list[str]:
        filtered: list[str] = []
        priority_urls: list[str] = []
        for url in urls:
            if any(re.search(p, url, re.IGNORECASE) for p in EXCLUDE_PATTERNS):
                continue
            path = urlparse(url).path.lower()
            if any(kw in path for kw in PRIORITY_KEYWORDS):
                priority_urls.append(url)
            else:
                filtered.append(url)
        return priority_urls + filtered

    def prioritize_links(self, links: list[str]) -> list[str]:
        keywords = (
            "sobre",
            "about",
            "quem-somos",
            "contato",
            "contact",
            "fale-conosco",
            "servico",
            "service",
            "servicos",
            "produto",
            "product",
            "produtos",
            "empresa",
            "company",
        )

        def score_url(url: str) -> float:
            path = urlparse(url).path.lower()
            matches = sum(1 for kw in keywords if kw in path)
            depth_penalty = path.count("/") * 0.1
            return matches - depth_penalty

        return sorted(links, key=score_url, reverse=True)

    def discover_pages_from_sitemap(self, base_url: str) -> list[str]:
        sitemap_paths = (
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap-index.xml",
            "/sitemap1.xml",
        )
        for sitemap_path in sitemap_paths:
            try:
                sitemap_url = urljoin(base_url, sitemap_path)
                response = requests.get(
                    sitemap_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                    verify=True,
                )
                if response.status_code != 200:
                    continue
                # html.parser works without lxml; suppress XML-as-HTML warning
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
                    soup = BeautifulSoup(response.content, "html.parser")
                urls = [loc.text.strip() for loc in soup.find_all("loc") if loc.text]
                if urls:
                    return self.filter_main_pages(urls[:200])
            except Exception as exc:
                logger.debug("Failed to fetch sitemap %s: %s", sitemap_path, exc)
                continue
        return []

    def discover_pages_from_homepage(self, base_url: str) -> list[str]:
        try:
            html = self.fetch_page_content(base_url)
            if not html:
                return []
            soup = BeautifulSoup(html, "html.parser")
            parsed_base = urlparse(base_url)
            base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
            nav_areas = soup.find_all(["nav", "header", "footer", "menu"])
            nav_areas.extend(
                soup.find_all(class_=re.compile(r"nav|menu|header", re.IGNORECASE))
            )
            links: set[str] = set()
            for area in nav_areas:
                for a_tag in area.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if not href or href.startswith(
                        ("#", "javascript:", "mailto:", "tel:")
                    ):
                        continue
                    full_url = urljoin(base_domain, href)
                    parsed_url = urlparse(full_url)
                    if parsed_url.netloc != parsed_base.netloc:
                        continue
                    clean_url = (
                        f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    )
                    clean_url = clean_url.rstrip("/")
                    if clean_url:
                        links.add(clean_url)
            if not links:
                return []
            return self.prioritize_links(list(links))
        except Exception as exc:
            logger.warning("Failed to crawl homepage navigation: %s", exc)
            return []

    def discover_pages_common_paths(self, base_url: str) -> list[str]:
        parsed = urlparse(base_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
        pages: list[str] = []
        for path in COMMON_PATHS:
            url = urljoin(base_domain, path)
            if url not in pages:
                pages.append(url)
        return pages[:MAX_PAGES_PER_SITE]

    def discover_pages(self, base_url: str) -> dict[str, str]:
        """Validate candidates and return top pages mapped to HTML content."""
        candidate_urls: set[str] = set()
        candidate_urls.update(self.discover_pages_from_homepage(base_url))
        candidate_urls.update(self.discover_pages_from_sitemap(base_url))
        candidate_urls.update(self.discover_pages_common_paths(base_url))

        valid_pages: list[tuple[str, str, int]] = []
        for idx, url in enumerate(candidate_urls):
            if idx > 0 and idx % 5 == 0:
                time.sleep(random.uniform(0.5, 1.5))
            html_content = self.fetch_page_content(url)
            if html_content:
                valid_pages.append((url, html_content, len(html_content)))

        if not valid_pages:
            return {}
        valid_pages.sort(key=lambda item: item[2], reverse=True)
        selected = valid_pages[:MAX_PAGES_PER_SITE]
        return {url: html for url, html, _ in selected}

    def crawl(self, website: str, polite: bool = True) -> CrawlResult:
        """Full crawl: robots → discover → return page HTML (cached from validation)."""
        self.stats = CrawlStats()
        try:
            base_url = normalize_url(website)
        except ValueError as exc:
            return CrawlResult(
                status="failed",
                status_reason=f"invalid_url: {exc}",
            )

        if not self.check_robots_txt(base_url):
            return CrawlResult(
                status="completed",
                status_reason="Scraping disallowed by robots.txt",
                base_url=base_url,
                stats=self.stats,
            )

        # Optional politeness pause before heavy discovery (no-op for first URL set)
        if polite:
            time.sleep(random.uniform(0.1, 0.3))

        pages = self.discover_pages(base_url)

        if not pages:
            status = "partial"
            reason = "No accessible pages fetched"
        elif self.stats.pages_failed:
            status = "partial"
            reason = "Some pages failed"
        else:
            status = "completed"
            reason = ""

        return CrawlResult(
            pages=pages,
            stats=self.stats,
            status=status,
            status_reason=reason,
            base_url=base_url,
        )
