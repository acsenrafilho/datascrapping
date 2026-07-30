"""Import all scrapers so they register themselves."""

from __future__ import annotations


def load_scrapers() -> None:
    # Blog scrapers (migrated from scrap_auditik)
    from datascrapping.scrapers import blog as _blog  # noqa: F401
    from datascrapping.scrapers import bni as _bni  # noqa: F401
    from datascrapping.scrapers import places as _places  # noqa: F401
