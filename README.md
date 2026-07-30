# datascrapping

CLI toolkit for structured web scraping and data collection.

Migrates the former [`scrap_auditik`](https://github.com/acsenrafilho/scrap_auditik) blog scrapers into a single Poetry-based project with a pluggable scraper registry. Prefer this repository going forward; `scrap_auditik` is deprecated.

## Setup

```bash
poetry install
cp .env.example .env
```

For BNI Connect (Playwright):

```bash
poetry install -E browser
poetry run playwright install chromium
```

Put credentials in `.env`:

```env
BNI_EMAIL=you@example.com
BNI_PASSWORD=secret
# Prospection Places key (separate from Lead Control SaaS Maps keys)
GOOGLE_PLACES_API_KEY=...
```

## Usage — blogs

```bash
poetry run datascrapping guide   # decision guide (blog / BNI / Places)
poetry run datascrapping list
poetry run datascrapping run --help   # flags: Shared / Blog / BNI / Places
poetry run datascrapping run blog.auditik
poetry run datascrapping run blog.concorrente \
  --url https://site.com/blog/ \
  --out minha_pasta
poetry run datascrapping run blog.concorrente \
  --url https://site.com/blog/ \
  --out minha_pasta \
  --pagination auto \
  --max-pages 30
poetry run datascrapping run blog.all --delay-min 1.5 --delay-max 4
```

`blog.concorrente` defaults to **auto** pagination and a stronger generic link classifier so it adapts better across WordPress-style blogs. Site-specific scrapers remain for harder layouts.

## Usage — BNI Connect

Target: [BNI search dashboard](https://www.bniconnectglobal.com/web/dashboard/search)

BNI directory search returns **at most ~250 results** per specialty query. Filters are optional (`--specialty`, `--category`, `--region`, `--country`, `--locale`).

- `--specialty` — one Search Category value (required shape from BNI’s list).
- `--category` — primary group (e.g. `Health & Wellness`). The BNI API ignores `category_id` alone, so the scraper expands the group into **one search per specialty** under it.
- `--country` / `--region` — geography (default country: Brazil).
- `--locale pt_BR|en|es` — language of API labels only (not geography).

```bash
# Discover valid specialty labels (EN / pt_BR / es)
poetry run datascrapping guide
poetry run datascrapping bni-specialties --groups-only
poetry run datascrapping bni-specialties
poetry run datascrapping bni-specialties --query fono --locale pt_BR
poetry run datascrapping bni-specialties -q hearing

# Any combination of filters (defaults: country=Brazil)
poetry run datascrapping run bni
poetry run datascrapping run bni --region SP
poetry run datascrapping run bni --specialty "Fonoaudiologia"
poetry run datascrapping run bni --specialty "Hearing/Audiology"
poetry run datascrapping run bni --category "Health & Wellness"
poetry run datascrapping run bni --category "Health & Wellness" --locale pt_BR

# Narrower cut with State + specialty
poetry run datascrapping run bni \
  --region SP \
  --specialty "Hearing/Audiology" \
  --country Brazil

# Consciously paginate every results page for that cut (slower / higher load)
poetry run datascrapping run bni \
  --specialty "Hearing/Audiology" \
  --all-pages

# Visible browser / force re-login (also for 2FA or CAPTCHA)
poetry run datascrapping run bni \
  --specialty "Hearing/Audiology" \
  --headed \
  --reauth
```

Example: Portuguese `Fonoaudiologia` maps to English UI `Hearing/Audiology` (same category id).
Outputs:

- CSV: `output/bni/<country>_<region|all>_<specialty|all>/members.csv`
- Checkpoint: `members.seen.json` (resume skips already collected profile URLs)
- Session: `output/.auth/bni_storage.json` (gitignored)

If BNI starts requiring 2FA/CAPTCHA, re-run with `--headed --reauth`, complete the challenge in the browser, then continue; the session is saved for later headless runs.

Use only with your own account and within BNI terms of use.

## Usage — Places (prospection)

Google Places API (New) Text Search + Place Details → commercial prospect CSV (name / phone / address). **Not** the Lead Control clinic Maps preview — use a separate GCP key in `GOOGLE_PLACES_API_KEY`.

Official Places API only (respect Google ToS). No HTML scrape of Maps. No Playwright / Gemini for stage 1.

```bash
# .env: GOOGLE_PLACES_API_KEY=...
poetry run datascrapping run places.search \
  --city "Campinas" --state SP --niche aasi

# Cap estimated quota units; skip IBGE city check; dry-run (no Places calls)
poetry run datascrapping run places.search \
  --city Americana --state SP --max-quota 5000
poetry run datascrapping run places.search \
  --city "Campinas" --state SP --skip-geo-check --dry-run
```

Outputs:

- CSV: `output/places/<city>_<uf>_<niche>/places.csv`
- Checkpoint: `places.seen.json` (resume skips `place_id`s already saved)

P0 columns: `name`, `phone` / `phone_intl`, `address` (+ `website`, `maps_url`, `place_id`). Column `email` is present but empty until a future `places.website` stage.

**Smoke (manual):** pick a small BR city, run niche `aasi`, confirm most rows have name + phone + address.

## Registered scrapers

| Name | Source |
|------|--------|
| `blog.auditik` | Auditik articles |
| `blog.communicare` | Communicare blog |
| `blog.essencial` | Essencial AASI blog |
| `blog.otoclinic` | Otoclinic blog |
| `blog.sonorita` | Sonorita blog |
| `blog.concorrente` | Generic URL + folder (auto pagination) |
| `blog.all` | Competitor set in sequence |
| `bni` | BNI Connect → CSV |
| `places.search` | Google Places → CSV (prospection) |

## Architecture

- `src/datascrapping/core/` — contract, registry, HTTP, browser helpers, sinks, checkpoint
- `src/datascrapping/scrapers/blog/` — blog crawlers
- `src/datascrapping/scrapers/bni/` — auth, search, profile, CSV orchestration
- `src/datascrapping/scrapers/places/` — Places Text Search + Details → CSV
- `src/datascrapping/cli.py` — Typer CLI

## Development

```bash
poetry run task lint
poetry run task test
```

## Deprecating scrap_auditik

All blog scraping scripts from `scrap_auditik` live here now. After validating this CLI, archive that repository on GitHub and point its README here.
