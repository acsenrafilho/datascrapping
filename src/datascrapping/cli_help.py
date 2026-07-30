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

# Sequential Places pipeline (stage → scraper → I/O → env).
PLACES_PIPELINE = (
    (
        "1",
        "places.search",
        "— (city/UF/niche)",
        "…/<slug>/places.csv",
        "GOOGLE_PLACES_API_KEY",
    ),
    (
        "2",
        "places.website",
        "places.csv (or folder)",
        "…/<slug>/places_enriched.csv",
        "optional GEMINI_API_KEY (+ poetry install -E llm)",
    ),
    (
        "3",
        "places.cnpj",
        "places_enriched.csv (or folder)",
        "…/<slug>/places_full.csv",
        "none (BrasilAPI public)",
    ),
    (
        "★",
        "places.all",
        "same as stage 1 (--city/--state)",
        "runs 1→2→3 → places_full.csv",
        "one command; --from computed from slug",
    ),
)

# Flag → which Places scraper(s) use it.
PLACES_FLAGS = (
    (
        "--city / --state",
        "places.search and places.all (required). e.g. Campinas SP",
    ),
    (
        "--niche",
        "places.search / places.all. Key in terms.json (default: aasi)",
    ),
    (
        "--skip-geo-check",
        "places.search / places.all. Skip BrasilAPI IBGE city/UF validation",
    ),
    (
        "--max-quota",
        "places.search / places.all. Cap estimated Places API units (default 20000)",
    ),
    (
        "--from",
        "places.website → places.csv; places.cnpj → places_enriched.csv "
        "(file or folder). Not needed for places.all (computed)",
    ),
    (
        "--skip-llm",
        "places.website / places.all. Heuristics only (no Gemini)",
    ),
    (
        "--cnpj",
        "places.cnpj only. Smoke one CNPJ, or filter rows with --from",
    ),
    (
        "--dry-run",
        "All stages / places.all: validate without writing "
        "(all dry-run only checks stage 1 + prints plan)",
    ),
)

PLACES_EXAMPLES = (
    (
        'run places.all --city "Campinas" --state SP --skip-llm',
        "★ Full pipeline ①→②→③ → …/campinas_sp_aasi/places_full.csv",
    ),
    (
        'run places.search --city "Campinas" --state SP',
        "① Places API → output/places/campinas_sp_aasi/places.csv",
    ),
    (
        "run places.website --from output/places/campinas_sp_aasi --skip-llm",
        "② Crawl sites (heuristics) → places_enriched.csv (same folder)",
    ),
    (
        "run places.cnpj --from output/places/campinas_sp_aasi",
        "③ BrasilAPI CNPJ → places_full.csv (razão social, CNAE, CEP fiscal)",
    ),
    (
        "run places.search --city Americana --state SP --niche aasi --max-quota 5000",
        "① Cap Places quota; niche from terms.json",
    ),
    (
        'run places.all --city "Campinas" --state SP --skip-geo-check --dry-run',
        "★ Dry-run: validate flags + print planned stages (no HTTP)",
    ),
    (
        "run places.website --from output/places/campinas_sp_aasi --dry-run",
        "② Dry-run: count rows with website; no HTTP",
    ),
    (
        "run places.cnpj --from output/places/campinas_sp_aasi --dry-run",
        "③ Dry-run: count rows with cnpj_raw; no HTTP",
    ),
    (
        "run places.cnpj --cnpj 19131243000197",
        "③ Smoke: one CNPJ → output/places/cnpj_manual/places_full.csv",
    ),
)
