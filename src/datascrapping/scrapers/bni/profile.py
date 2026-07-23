from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from datascrapping.scrapers.bni.models import BniMember

logger = logging.getLogger(__name__)

_SKIP_HOST_FRAGMENTS = (
    "bniconnectglobal.com",
    "bniconnect.com",
    "bni.com",
    "support.bniconnect",
)


def _text_or_empty(page, selectors: list[str]) -> str:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = locator.inner_text().strip()
            if text:
                return re.sub(r"\s+", " ", text)
        except Exception:
            continue
    return ""


def _attr_or_empty(page, selectors: list[str], attr: str) -> str:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            value = locator.get_attribute(attr)
            if value:
                return value.strip()
        except Exception:
            continue
    return ""


def _labeled_value(page, labels: list[str]) -> str:
    for label in labels:
        try:
            node = page.locator(
                f"xpath=//*[self::dt or self::label or self::span or self::div]"
                f"[contains(translate(normalize-space(.),"
                f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
                f"'{label.lower()}')]"
            ).first
            if node.count() == 0:
                continue
            sibling = node.locator("xpath=following-sibling::*[1]").first
            if sibling.count():
                text = sibling.inner_text().strip()
                if text and text.lower() != label.lower():
                    return re.sub(r"\s+", " ", text)
        except Exception:
            continue
        try:
            by_label = page.get_by_label(re.compile(label, re.I)).first
            if by_label.count():
                tag = by_label.evaluate("el => el.tagName").lower()
                if tag in {"input", "textarea"}:
                    return (by_label.input_value() or "").strip()
                return by_label.inner_text().strip()
        except Exception:
            continue
    return ""


def _external_website(page) -> str:
    anchors = page.locator("a[href^='http']")
    count = anchors.count()
    for index in range(count):
        try:
            href = anchors.nth(index).get_attribute("href") or ""
        except Exception:
            continue
        if not href:
            continue
        host = urlparse(href).netloc.lower()
        if any(frag in host for frag in _SKIP_HOST_FRAGMENTS):
            continue
        return href
    return ""


def enrich_member_contacts(page, member: BniMember) -> BniMember:
    """Open member profile and fill email/phone/website when missing."""
    if not member.profile_url:
        return member

    page.goto(member.profile_url, wait_until="domcontentloaded")
    try:
        page.wait_for_url(re.compile(r".*/web/member.*"), timeout=20_000)
    except Exception:
        page.wait_for_timeout(2000)

    # Contact block often hydrates after first paint.
    try:
        page.locator('a[href^="mailto:"], a[href^="tel:"]').first.wait_for(
            state="attached", timeout=8_000
        )
    except Exception:
        page.wait_for_timeout(2000)

    body = ""
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""

    if not member.name:
        headings = page.locator("h1, h2, h3, h4")
        for index in range(min(headings.count(), 8)):
            text = headings.nth(index).inner_text().strip()
            if not text or text.casefold() in {"perfil", "profile"}:
                continue
            member.name = re.sub(r"\s+", " ", text)
            break

    if not member.email:
        member.email = _attr_or_empty(page, ['a[href^="mailto:"]'], "href").replace(
            "mailto:", ""
        )
        if not member.email:
            match = re.search(
                r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
                body,
                re.I,
            )
            if match:
                member.email = match.group(0)

    if not member.phone:
        member.phone = _attr_or_empty(page, ['a[href^="tel:"]'], "href").replace(
            "tel:", ""
        ) or _labeled_value(
            page, ["phone", "telephone", "mobile", "telefone", "celular"]
        )

    if not member.website:
        member.website = _external_website(page) or _labeled_value(
            page, ["website", "web site", "site"]
        )

    if not member.company:
        member.company = _labeled_value(
            page, ["company", "empresa", "business"]
        ) or _text_or_empty(page, [".company", "[class*='company' i]"])

    if not member.chapter:
        member.chapter = _labeled_value(
            page, ["chapter", "capítulo", "capitulo", "grupo"]
        )

    if not member.specialty:
        match = re.search(
            r"(?:Detalhes da Profissão|Profession Details)\s*(.+?)"
            r"(?:\n\n|Histórico|Training|$)",
            body,
            re.I | re.S,
        )
        if match:
            member.specialty = re.sub(r"\s+", " ", match.group(1)).strip()

    logger.info(
        "Enriched profile: %s email=%s phone=%s",
        member.name or "?",
        bool(member.email),
        bool(member.phone),
    )
    return member


def extract_member_profile(page, profile_url: str) -> BniMember:
    member = BniMember(profile_url=profile_url)
    return enrich_member_contacts(page, member)
