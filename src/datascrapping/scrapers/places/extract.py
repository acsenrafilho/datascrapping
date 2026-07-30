"""Cheap heuristic contact extraction for places.website (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
# Avoid common false positives in assets / tracking
EMAIL_EXCLUDE_RE = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|css|js)$",
    re.IGNORECASE,
)

PHONE_RE = re.compile(
    r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9?\d{4}[\s\-]?\d{4})",
)

CNPJ_FORMATTED_RE = re.compile(
    r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}",
)

SOCIAL_HOSTS = {
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "linkedin": ("linkedin.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "twitter": ("twitter.com", "x.com"),
}


@dataclass
class HeuristicExtraction:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    cnpj_raw: str = ""
    social: dict[str, str] = field(default_factory=dict)
    brand_name: str = ""


def _normalize_email(raw: str) -> str | None:
    email = unquote(raw).strip().strip(".,;:<>()[]\"'")
    email = email.replace("mailto:", "", 1) if email.lower().startswith("mailto:") else email
    if "?" in email:
        email = email.split("?", 1)[0]
    email = email.strip().lower()
    if not email or "@" not in email:
        return None
    if EMAIL_EXCLUDE_RE.search(email):
        return None
    if not EMAIL_RE.fullmatch(email):
        return None
    return email


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def clean_cnpj_digits(value: str) -> str | None:
    digits = _digits_only(value)
    if len(digits) != 14:
        return None
    if digits == digits[0] * 14:
        return None
    return digits


def format_cnpj(digits: str) -> str:
    d = _digits_only(digits)
    if len(d) != 14:
        return digits
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _is_valid_cnpj_check_digits(digits: str) -> bool:
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    def check(partial: str, weights: list[int]) -> int:
        total = sum(int(d) * w for d, w in zip(partial, weights))
        rem = total % 11
        return 0 if rem < 2 else 11 - rem

    if int(digits[12]) != check(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        return False
    if int(digits[13]) != check(digits[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        return False
    return True


def extract_mailto_emails(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href.lower().startswith("mailto:"):
            continue
        email = _normalize_email(href[7:])
        if email:
            found.append(email)
    return found


def extract_emails_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in EMAIL_RE.findall(text or ""):
        email = _normalize_email(match)
        if email:
            found.append(email)
    return found


def extract_phones_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in PHONE_RE.findall(text or ""):
        digits = _digits_only(match)
        # BR local 8–9 digits, or with DDD 10–11, or with country 12–13
        if len(digits) < 8 or len(digits) > 13:
            continue
        cleaned = re.sub(r"\s+", " ", match.strip())
        if cleaned not in found:
            found.append(cleaned)
    return found


def extract_cnpj_from_text(text: str) -> str:
    for match in CNPJ_FORMATTED_RE.findall(text or ""):
        digits = clean_cnpj_digits(match)
        if not digits:
            continue
        if _is_valid_cnpj_check_digits(digits):
            return format_cnpj(digits)
        # accept 14-digit lookalikes that fail check-digit only as raw formatted
        return format_cnpj(digits)
    return ""


def extract_social_links(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            host = urlparse(href).netloc.lower()
        except Exception:
            continue
        host = host.removeprefix("www.")
        for network, hosts in SOCIAL_HOSTS.items():
            if network in found:
                continue
            if any(host == h or host.endswith("." + h) for h in hosts):
                found[network] = href
    return found


def extract_brand_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # common "Brand | Home" / "Brand - Contato"
        for sep in ("|", "–", "-", "—"):
            if sep in title:
                return title.split(sep, 1)[0].strip()[:120]
        return title[:120]
    return ""


def extract_from_pages(pages: dict[str, str]) -> HeuristicExtraction:
    """Run heuristics across crawled HTML pages."""
    emails: list[str] = []
    phones: list[str] = []
    social: dict[str, str] = {}
    cnpj_raw = ""
    brand_name = ""

    for html in pages.values():
        emails.extend(extract_mailto_emails(html))
        emails.extend(extract_emails_from_text(html))
        phones.extend(extract_phones_from_text(html))
        for network, url in extract_social_links(html).items():
            social.setdefault(network, url)
        if not cnpj_raw:
            cnpj_raw = extract_cnpj_from_text(html)
        if not brand_name:
            brand_name = extract_brand_from_html(html)

    # de-dupe emails preserving order
    seen_e: set[str] = set()
    uniq_emails: list[str] = []
    for email in emails:
        if email not in seen_e:
            seen_e.add(email)
            uniq_emails.append(email)

    seen_p: set[str] = set()
    uniq_phones: list[str] = []
    for phone in phones:
        key = _digits_only(phone)
        if key and key not in seen_p:
            seen_p.add(key)
            uniq_phones.append(phone)

    return HeuristicExtraction(
        emails=uniq_emails,
        phones=uniq_phones[:8],
        cnpj_raw=cnpj_raw,
        social=social,
        brand_name=brand_name,
    )
