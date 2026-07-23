from __future__ import annotations

from datascrapping.core.registry import register
from datascrapping.scrapers.blog.base_blog import (
    BlogScraper,
    default_classify_article_link,
)


@register
class ConcorrenteBlogScraper(BlogScraper):
    """Generic blog scraper: requires --url and --out via CLI extras."""

    name = "blog.concorrente"
    description = (
        "Generic blog crawl (--url/--out; pagination auto by default)"
    )
    listing_url = ""
    output_subdir = "concorrente"
    pagination_mode = "auto"
    max_listing_pages = 50
    classify_fn = staticmethod(default_classify_article_link)
