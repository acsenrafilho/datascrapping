from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from datascrapping.core.browser import save_storage_state, wait_for_manual_challenge
from datascrapping.core.config import env
from datascrapping.scrapers.bni.models import BNI_HOME_URL, BNI_LOGIN_URL

logger = logging.getLogger(__name__)

CHALLENGE_URL_HINTS = (
    "captcha",
    "recaptcha",
    "2fa",
    "mfa",
    "otp",
    "verify",
    "challenge",
    "two-factor",
    "twofactor",
    "security-check",
)


def looks_like_challenge(url: str, page_text: str = "") -> bool:
    haystack = f"{url} {page_text}".lower()
    return any(hint in haystack for hint in CHALLENGE_URL_HINTS)


def is_authenticated(page) -> bool:
    url = page.url.lower()
    if "/login" in url or "/signin" in url:
        return False
    # Dashboard / search / member areas indicate a session
    if any(
        token in url
        for token in ("/web/dashboard", "/web/home", "/web/member", "/web/")
    ):
        # Still on marketing root without session is possible; check logout cue
        try:
            if page.locator("text=/log\\s*out|sign\\s*out/i").count() > 0:
                return True
        except Exception:
            pass
        if "/web/dashboard" in url or "/web/member" in url:
            return True
    return False


def _fill_first(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            locator.wait_for(state="visible", timeout=5_000)
            locator.fill(value)
            return True
        except Exception:
            continue
    return False


def _click_first(page, selectors: list[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            locator.wait_for(state="visible", timeout=5_000)
            locator.click()
            return True
        except Exception:
            continue
    return False


def ensure_authenticated(
    page,
    context,
    *,
    storage_path: Path,
    headed: bool,
    reauth: bool,
) -> None:
    """Login if needed; handle 2FA/CAPTCHA with headed pause fallback."""
    email = env("BNI_EMAIL")
    password = env("BNI_PASSWORD")

    if not reauth and storage_path.exists():
        page.goto(BNI_HOME_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        if is_authenticated(page) and not looks_like_challenge(page.url):
            logger.info("Existing BNI session looks valid")
            return
        logger.info("Stored session expired or invalid; logging in again")

    if not email or not password:
        raise ValueError(
            "Missing BNI_EMAIL / BNI_PASSWORD in environment or .env"
        )

    page.goto(BNI_LOGIN_URL, wait_until="domcontentloaded")
    # SPA form renders after first paint; wait for username/password fields.
    try:
        page.locator(
            'input[name="username"], input[name="password"], '
            'input[type="password"]'
        ).first.wait_for(state="visible", timeout=30_000)
    except Exception as exc:
        raise RuntimeError(
            "BNI login form did not appear. "
            "Try --headed to inspect the page and update selectors in auth.py."
        ) from exc

    # BNI Connect uses Username (not email) + Password.
    filled_email = _fill_first(
        page,
        [
            'input[name="username"]',
            'input[placeholder*="Username" i]',
            'input[name*="user" i]',
            'input[type="email"]',
            'input[name*="email" i]',
            'input[id*="email" i]',
            'input[placeholder*="email" i]',
            'input[type="text"]',
        ],
        email,
    )
    filled_password = _fill_first(
        page,
        [
            'input[name="password"]',
            'input[type="password"]',
            'input[id*="password" i]',
            'input[placeholder*="Password" i]',
        ],
        password,
    )
    if not filled_email or not filled_password:
        raise RuntimeError(
            "Could not locate BNI login fields. "
            "Try --headed to inspect the page and update selectors in auth.py."
        )

    clicked = _click_first(
        page,
        [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("SIGN IN")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Entrar")',
        ],
    )
    if not clicked:
        page.keyboard.press("Enter")

    page.wait_for_timeout(2500)
    body_text = ""
    try:
        body_text = page.inner_text("body")[:4000]
    except Exception:
        pass

    if looks_like_challenge(page.url, body_text) or not is_authenticated(page):
        # May still be loading; wait a bit for redirect
        try:
            page.wait_for_url(
                re.compile(r".*/web/.*"),
                timeout=15_000,
            )
        except Exception:
            pass
        body_text = ""
        try:
            body_text = page.inner_text("body")[:4000]
        except Exception:
            pass

    if looks_like_challenge(page.url, body_text) or (
        not is_authenticated(page) and "login" not in page.url.lower()
    ):
        message = (
            "BNI login requires manual verification (2FA/CAPTCHA or similar).\n"
            "A headed browser session is required. Complete the challenge, "
            "wait until you reach the dashboard, then resume."
        )
        if not headed:
            raise RuntimeError(
                message
                + "\nRe-run with: poetry run datascrapping run bni "
                "--specialty … [--region …] --headed --reauth"
            )
        wait_for_manual_challenge(page, message=message)
        # Wait until we leave login / challenge
        for _ in range(120):
            if is_authenticated(page) and not looks_like_challenge(page.url):
                break
            page.wait_for_timeout(1000)
        else:
            raise RuntimeError(
                "Timed out waiting for manual BNI challenge completion"
            )

    if not is_authenticated(page):
        # Final attempt: maybe login succeeded but detection failed
        path = urlparse(page.url).path.lower()
        if "/login" in path:
            raise RuntimeError(
                "BNI login failed. Check credentials or use --headed --reauth."
            )

    save_storage_state(context, storage_path)
