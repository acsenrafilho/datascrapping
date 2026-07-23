from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScrapeContext:
    """Runtime options shared by every scraper run."""

    out_dir: Path
    delay_min: float = 1.0
    delay_max: float = 3.0
    dry_run: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Summary returned after a scraper finishes."""

    scraper: str
    saved: int = 0
    skipped: int = 0
    errors: int = 0
    output_path: Path | None = None
    message: str = ""


class BaseScraper(ABC):
    """Contract every scraper must implement."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        """Execute the scrape and return a summary."""
