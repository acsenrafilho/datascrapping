"""Static help copy for CLI guide / --help panels."""

from __future__ import annotations

# Primary Search Category groups from BNI (locale=en). Full specialty
# labels change over time — use `bni-specialties` for the live list.
BNI_CATEGORY_GROUPS = (
    "Advertising & Marketing",
    "Agriculture",
    "Animals",
    "Architecture & Engineering",
    "Art & Entertainment",
    "BNI",
    "Car & Motorcycle",
    "Computer & Programming",
    "Construction",
    "Consulting",
    "Employment Activities",
    "Event & Business Service",
    "Finance & Insurance",
    "Food & Beverage",
    "Health & Wellness",
    "Legal & Accounting",
    "Manufacturing",
    "Organizations & Others",
    "Personal Services",
    "Real Estate Services",
    "Repair",
    "Retail",
    "Security & Investigation",
    "Sports & Leisure",
    "Telecommunications",
    "Training & Coaching",
    "Transport & Shipping",
    "Travel",
)

BNI_SPECIALTY_EXAMPLES = (
    ("Hearing/Audiology", "Fonoaudiologia", "Health & Wellness"),
    ("Hearing Aids", "—", "Retail / related"),
    ("Marketing Consultant", "—", "Advertising & Marketing"),
)

BLOG_PAGINATION_MODES = (
    ("auto", "Detect numbered vs BFS from the listing HTML (default)."),
    ("simple", "Only the starting listing URL (no pagination walk)."),
    ("numbered", "Follow page/2, page/3, ?paged=N style links."),
    ("bfs", "Breadth-first crawl of same-site listing-like pages."),
)

SHARED_DEFAULTS = (
    ("--out-dir", "OUTPUT_DIR from .env, else ./output"),
    ("--delay-min/--delay-max", "SCRAPE_DELAY_* from .env, else 1.0–3.0s"),
    ("BNI delays", "If you leave env defaults, BNI bumps to ~3.0–8.0s"),
)
