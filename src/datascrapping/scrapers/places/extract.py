"""Cheap heuristic contact extraction for places.website (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

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

# wa.me/5516999999999 or path segment with digits
WA_ME_PATH_RE = re.compile(r"/(\+?\d{10,15})")

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
    whatsapp: str = ""
    whatsapp_url: str = ""


def _normalize_email(raw: str) -> str | None:
    email = unquote(raw).strip().strip(".,;:<>()[]\"'")
    email = (
        email.replace("mailto:", "", 1)
        if email.lower().startswith("mailto:")
        else email
    )
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


def normalize_whatsapp_digits(raw: str) -> str:
    """Normalize to digits; prefer BR E.164 (55 + DDD + number) when length fits."""
    digits = _digits_only(raw)
    if not digits:
        return ""
    digits = digits.lstrip("0") or digits
    if len(digits) in (10, 11):
        return "55" + digits
    if len(digits) in (12, 13) and digits.startswith("55"):
        return digits
    if 10 <= len(digits) <= 15:
        return digits
    return ""


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


def validate_cnpj(value: str) -> bool:
    """Return True if value has 14 digits and valid CNPJ check digits."""
    digits = clean_cnpj_digits(value)
    if not digits:
        return False
    return _is_valid_cnpj_check_digits(digits)


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


def extract_tel_links(html: str) -> list[str]:
    """Extract phone numbers from tel: hrefs."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href.lower().startswith("tel:"):
            continue
        raw = unquote(href[4:]).strip()
        digits = _digits_only(raw)
        if 8 <= len(digits) <= 15:
            cleaned = re.sub(r"\s+", " ", raw.strip())
            if cleaned and cleaned not in found:
                found.append(cleaned)
    return found


def _whatsapp_from_href(href: str) -> tuple[str, str] | None:
    """Return (digits, original_url) if href is a WhatsApp link."""
    raw = href.strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw if "://" in raw else "https://" + raw.lstrip("/"))
    except Exception:
        return None
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path or ""
    query = parse_qs(parsed.query or "")

    digits = ""
    if "wa.me" in host or host.endswith("wa.me"):
        match = WA_ME_PATH_RE.search(path)
        if match:
            digits = normalize_whatsapp_digits(match.group(1))
    elif "api.whatsapp.com" in host or host.endswith("whatsapp.com"):
        if query.get("phone"):
            digits = normalize_whatsapp_digits(query["phone"][0])
    elif "whatsapp" in host and query.get("phone"):
        digits = normalize_whatsapp_digits(query["phone"][0])

    if not digits:
        return None
    url_out = raw if "://" in raw else f"https://wa.me/{digits}"
    return digits, url_out


def extract_whatsapp_from_html(html: str) -> tuple[str, str]:
    """Return (digits, first_url) for WhatsApp links in HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        result = _whatsapp_from_href(a_tag["href"].strip())
        if result:
            return result
    for match in re.finditer(
        r"https?://(?:wa\.me|api\.whatsapp\.com|www\.whatsapp\.com)/[^\s\"'<>]+",
        html or "",
        re.IGNORECASE,
    ):
        result = _whatsapp_from_href(match.group(0))
        if result:
            return result
    return "", ""


def extract_meta_text(html: str) -> str:
    """Collect og:description, og:title, meta description, title for bio-like text."""
    soup = BeautifulSoup(html, "html.parser")
    chunks: list[str] = []
    for prop in ("og:description", "og:title", "twitter:description", "description"):
        tag = soup.find("meta", property=prop) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            chunks.append(str(tag["content"]).strip())
    if soup.title and soup.title.string:
        chunks.append(soup.title.string.strip())
    return "\n".join(c for c in chunks if c)


def extract_cnpj_from_text(text: str) -> str:
    for match in CNPJ_FORMATTED_RE.findall(text or ""):
        digits = clean_cnpj_digits(match)
        if not digits:
            continue
        if _is_valid_cnpj_check_digits(digits):
            return format_cnpj(digits)
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
            lower_host = urlparse(href).netloc.lower().removeprefix("www.")
        except Exception:
            continue
        if "wa.me" in lower_host or "api.whatsapp.com" in lower_host:
            continue
        for network, hosts in SOCIAL_HOSTS.items():
            if network in found:
                continue
            if any(lower_host == h or lower_host.endswith("." + h) for h in hosts):
                found[network] = href
    return found


def extract_brand_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        for sep in ("|", "–", "-", "—"):
            if sep in title:
                return title.split(sep, 1)[0].strip()[:120]
        return title[:120]
    return ""


def extract_contacts_from_html(html: str) -> dict[str, Any]:
    """Extract emails, phones, whatsapp from a single HTML blob (site or social)."""
    emails = extract_mailto_emails(html) + extract_emails_from_text(html)
    meta = extract_meta_text(html)
    if meta:
        emails.extend(extract_emails_from_text(meta))
    phones = extract_phones_from_text(html) + extract_tel_links(html)
    if meta:
        phones.extend(extract_phones_from_text(meta))
    wa_digits, wa_url = extract_whatsapp_from_html(html)
    if not wa_digits and meta:
        for match in re.finditer(
            r"(?:wa\.me/|whatsapp\.com/send\?phone=)(\+?\d{10,15})",
            meta,
            re.IGNORECASE,
        ):
            wa_digits = normalize_whatsapp_digits(match.group(1))
            if wa_digits:
                wa_url = f"https://wa.me/{wa_digits}"
                break
    return {
        "emails": emails,
        "phones": phones,
        "whatsapp": wa_digits,
        "whatsapp_url": wa_url,
        "meta_text": meta,
    }


def extract_from_pages(pages: dict[str, str]) -> HeuristicExtraction:
    """Run heuristics across crawled HTML pages."""
    emails: list[str] = []
    phones: list[str] = []
    social: dict[str, str] = {}
    cnpj_raw = ""
    brand_name = ""
    whatsapp = ""
    whatsapp_url = ""

    for html in pages.values():
        emails.extend(extract_mailto_emails(html))
        emails.extend(extract_emails_from_text(html))
        phones.extend(extract_phones_from_text(html))
        phones.extend(extract_tel_links(html))
        if not whatsapp:
            whatsapp, whatsapp_url = extract_whatsapp_from_html(html)
        for network, url in extract_social_links(html).items():
            social.setdefault(network, url)
        if not cnpj_raw:
            cnpj_raw = extract_cnpj_from_text(html)
        if not brand_name:
            brand_name = extract_brand_from_html(html)

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
        whatsapp=whatsapp,
        whatsapp_url=whatsapp_url,
    )
