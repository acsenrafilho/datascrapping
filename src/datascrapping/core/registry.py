from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datascrapping.core.base import BaseScraper


class ScraperRegistry:
    """In-memory registry of scrapers keyed by dotted name."""

    def __init__(self) -> None:
        self._scrapers: dict[str, type[BaseScraper]] = {}

    def register(self, scraper_cls: type[BaseScraper]) -> type[BaseScraper]:
        name = scraper_cls.name
        if not name or name == "base":
            raise ValueError(f"Scraper {scraper_cls!r} must define a unique name")
        existing = self._scrapers.get(name)
        if existing is not None and existing is not scraper_cls:
            raise ValueError(f"Scraper already registered: {name}")
        self._scrapers[name] = scraper_cls
        return scraper_cls

    def get(self, name: str) -> type[BaseScraper]:
        try:
            return self._scrapers[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._scrapers)) or "(none)"
            raise KeyError(
                f"Unknown scraper '{name}'. Available: {known}"
            ) from exc

    def list(self) -> list[tuple[str, str]]:
        items = [
            (name, cls.description or "")
            for name, cls in self._scrapers.items()
        ]
        return sorted(items, key=lambda item: item[0])

    def names(self) -> list[str]:
        return sorted(self._scrapers)


registry = ScraperRegistry()


def register(scraper_cls: type[BaseScraper]) -> type[BaseScraper]:
    """Decorator to register a scraper class."""
    return registry.register(scraper_cls)
