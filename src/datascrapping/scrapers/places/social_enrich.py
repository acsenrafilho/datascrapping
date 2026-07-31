"""Best-effort HTTP fetch of social profile URLs for contact enrichment."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import requests

from datascrapping.scrapers.places.crawl import USER_AGENT
from datascrapping.scrapers.places.extract import extract_contacts_from_html

logger = logging.getLogger(__name__)

SOCIAL_NETWORKS = (
    "facebook",
    "instagram",
    "linkedin",
    "youtube",
    "tiktok",
    "twitter",
)

REQUEST_TIMEOUT = 8
MIN_DELAY = 1.0
MAX_DELAY = 2.0

LOGIN_WALL_MARKERS = (
    "log in",
    "login",
    "sign in",
    "entrar",
    "criar uma conta",
    "create an account",
    "joined linkedin",
    "agree to our terms",
)


@dataclass
class SocialEnrichResult:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    whatsapp: str = ""
    whatsapp_url: str = ""
    status_parts: list[str] = field(default_factory=list)
    meta_texts: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "|".join(self.status_parts)


def _looks_like_login_wall(html: str, meta: str) -> bool:
    sample = f"{meta}\n{html[:4000]}".lower()
    hits = sum(1 for marker in LOGIN_WALL_MARKERS if marker in sample)
    # Many platforms return a short login shell with little bio content
    if hits >= 2 and len(meta) < 80:
        return True
    if "login" in sample and "password" in sample and len(meta) < 40:
        return True
    return False


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def fetch_social_html(
    url: str,
    *,
    http_get: Callable[..., requests.Response] | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[str | None, str]:
    """GET social URL. Returns (html_or_none, status_token)."""
    get = http_get or requests.get
    try:
        response = get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return None, "timeout"
    except requests.exceptions.RequestException:
        return None, "failed_http"

    if response.status_code in (401, 403):
        return None, "blocked"
    if response.status_code >= 400:
        return None, f"http_{response.status_code}"

    text = response.text or ""
    if not text.strip():
        return None, "empty"
    return text, "ok"


def enrich_from_social_urls(
    social_urls: dict[str, str],
    *,
    http_get: Callable[..., requests.Response] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    polite: bool = True,
) -> SocialEnrichResult:
    """Fetch each non-empty social URL once and extract contacts best-effort."""
    result = SocialEnrichResult()
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()

    for network in SOCIAL_NETWORKS:
        url = (social_urls.get(network) or "").strip()
        if not url:
            continue
        url = _normalize_url(url)
        try:
            host = urlparse(url).netloc
            if not host:
                result.status_parts.append(f"{network}:invalid_url")
                continue
        except Exception:
            result.status_parts.append(f"{network}:invalid_url")
            continue

        if polite:
            sleep_fn(random.uniform(MIN_DELAY, MAX_DELAY))

        html, fetch_status = fetch_social_html(url, http_get=http_get)
        if html is None:
            result.status_parts.append(f"{network}:{fetch_status}")
            continue

        contacts = extract_contacts_from_html(html)
        meta = contacts.get("meta_text") or ""
        if meta:
            result.meta_texts.append(meta)

        if _looks_like_login_wall(html, meta) and not (
            contacts["emails"] or contacts["phones"] or contacts["whatsapp"]
        ):
            result.status_parts.append(f"{network}:blocked")
            continue

        got_contact = False
        for email in contacts["emails"]:
            key = email.lower().strip()
            if key and key not in seen_emails:
                seen_emails.add(key)
                result.emails.append(key)
                got_contact = True
        for phone in contacts["phones"]:
            key = "".join(c for c in phone if c.isdigit())
            if key and key not in seen_phones:
                seen_phones.add(key)
                result.phones.append(phone)
                got_contact = True
        if contacts["whatsapp"] and not result.whatsapp:
            result.whatsapp = contacts["whatsapp"]
            result.whatsapp_url = contacts["whatsapp_url"]
            got_contact = True

        if got_contact:
            result.status_parts.append(f"{network}:ok")
        elif meta:
            result.status_parts.append(f"{network}:no_contact")
        else:
            result.status_parts.append(f"{network}:empty")

    return result
