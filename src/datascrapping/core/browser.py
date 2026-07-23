from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class BrowserUnavailableError(RuntimeError):
    """Raised when Playwright is not installed."""


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailableError(
            "Playwright is not installed. Run:\n"
            "  poetry install -E browser\n"
            "  poetry run playwright install chromium"
        ) from exc
    return sync_playwright


@contextmanager
def browser_session(
    *,
    headed: bool = False,
    storage_state: Path | None = None,
    user_agent: str | None = None,
) -> Iterator[tuple]:
    """Yield (playwright, browser, context, page).

    If ``storage_state`` exists, the context is created with that session.
    """
    sync_playwright = _import_playwright()
    headless = not headed
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context_kwargs: dict = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
        }
        if user_agent:
            context_kwargs["user_agent"] = user_agent
        if storage_state and storage_state.exists():
            context_kwargs["storage_state"] = str(storage_state)
            logger.info("Loaded browser storageState from %s", storage_state)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(45_000)
        try:
            yield playwright, browser, context, page
        finally:
            context.close()
            browser.close()


def save_storage_state(context, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    logger.info("Saved browser storageState to %s", path)
    return path


def wait_for_manual_challenge(page, *, message: str) -> None:
    """Pause for the operator to complete 2FA/CAPTCHA in a headed browser."""
    logger.warning(message)
    print("\n" + "=" * 60)
    print(message)
    print("Complete the challenge in the browser window, then press Enter here.")
    print("=" * 60 + "\n")
    try:
        # Inspector pause if available (headed Playwright)
        page.pause()
    except Exception:
        input("Press Enter after completing the challenge… ")
