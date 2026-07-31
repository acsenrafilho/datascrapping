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

Three stage scrapers **in order**, or one-shot **`places.all`**. Folder slug:
`output/places/<city>_<uf>_<niche>/` (e.g. `campinas_sp_aasi`).

| Stage | Scraper | Input | Output | Env |
|------|---------|-------|--------|-----|
| ① | `places.search` | `--city` / `--state` / `--niche` | `places.csv` | `GOOGLE_PLACES_API_KEY` |
| ② | `places.website` | `--from` → `places.csv` or folder | `places_enriched.csv` | optional `GEMINI_API_KEY` + `poetry install -E llm` |
| ③ | `places.cnpj` | `--from` → `places_enriched.csv` or folder | `places_full.csv` | none (BrasilAPI) |
| ★ | `places.all` | same as ① (+ `--skip-llm`) | runs ①→②→③ → `places_full.csv` | `--from` computed from slug |

Official Places API only for stage 1 (respect Google ToS). No HTML scrape of Maps. No Playwright for Places. CEP / endereço fiscal come from BrasilAPI CNPJ in stage 3 (not ViaCEP).

CLI docs for the same pipeline:

```bash
poetry run datascrapping guide          # §6 Places: table, flags, full recipe
poetry run datascrapping list           # includes places.all
poetry run datascrapping run --help     # Places flags marked ①/②/③ + places.all
```

### One-shot — `places.all` (recommended for a new city)

Runs search → website → cnpj. Same flags as stage 1, plus `--skip-llm` for heuristics-only website crawl. Does **not** take `--from` (folder is derived from city/UF/niche).

```bash
# .env: GOOGLE_PLACES_API_KEY=...
poetry run datascrapping run places.all \
  --city "Campinas" --state SP --niche aasi --skip-llm

# Validate plan without HTTP (prints the three stages + output folder)
poetry run datascrapping run places.all \
  --city "Campinas" --state SP --skip-geo-check --dry-run

# With Gemini on stage 2 (optional)
# poetry install -E llm && GEMINI_API_KEY=...
poetry run datascrapping run places.all \
  --city "Campinas" --state SP
```

If stage 1 already ran, re-running `places.all` resumes via checkpoints (skips known `place_id`s) and continues into website + cnpj. To run only the remaining stages without calling Places again:

```bash
poetry run datascrapping run places.website \
  --from output/places/campinas_sp_aasi --skip-llm
poetry run datascrapping run places.cnpj \
  --from output/places/campinas_sp_aasi
```

### Stage by stage (manual)

```bash
poetry run datascrapping run places.search \
  --city "Campinas" --state SP --niche aasi

poetry run datascrapping run places.website \
  --from output/places/campinas_sp_aasi --skip-llm

poetry run datascrapping run places.cnpj \
  --from output/places/campinas_sp_aasi
```

### Stage 1 — `places.search`

```bash
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

P0 columns: `name`, `phone` / `phone_intl`, `address` (+ `website`, `maps_url`, `place_id`). Column `email` is empty until stage 2.

### Stage 2 — `places.website` (e-mail / enrichment)

Reads `places.csv`, crawls each non-empty `website` (robots.txt, sitemap/nav/common paths, polite delays), extracts contacts with **cheap heuristics first** (`mailto:`, e-mail/phone/CNPJ/social), then optionally fills gaps with Gemini.

```bash
# Heuristics only (no Gemini)
poetry run datascrapping run places.website \
  --from output/places/campinas_sp_aasi --skip-llm

# Optional LLM fill-gaps
# poetry install -E llm
# .env: GEMINI_API_KEY=...
poetry run datascrapping run places.website \
  --from output/places/campinas_sp_aasi/places.csv
```

Outputs:

- CSV: `places_enriched.csv` (same folder as input)
- Checkpoint: `places.website.seen.json` (resume by `place_id`)

Extra columns include `email`, `emails_extra`, `phones_extra`, `cnpj_raw`, `whatsapp`, `whatsapp_url`, `social_*` (profile URLs), `social_enrich_status` (best-effort HTTP on those profiles — IG/FB/LinkedIn often login-wall), `brand_name`, `website_status`, `website_scraped_at`, `pages_fetched`, `pages_failed`.

WhatsApp links (`wa.me` / `api.whatsapp.com`) and `tel:` hrefs are extracted from the company site; social profile pages are fetched once each (no login / no Playwright) to pull bio/meta contacts when available.

Respect `robots.txt` and site ToS. Gemini is optional and fail-soft if the `llm` extra or key is missing.

### Stage 3 — `places.cnpj` (federal registry)

Reads `places_enriched.csv`, looks up each non-empty `cnpj_raw` on BrasilAPI (`GET /api/cnpj/v1/{cnpj}`), and writes commercial federal fields (incl. `fiscal_cep`). Fail-closed on invalid CNPJ (row still emitted with `cnpj_status=skipped_invalid`). No API key required.

```bash
poetry run datascrapping run places.cnpj \
  --from output/places/campinas_sp_aasi

# Explicit file
poetry run datascrapping run places.cnpj \
  --from output/places/campinas_sp_aasi/places_enriched.csv

# Smoke: single CNPJ (no CSV)
poetry run datascrapping run places.cnpj --cnpj 19131243000197

# Dry-run (count rows with cnpj_raw; no HTTP)
poetry run datascrapping run places.cnpj \
  --from output/places/campinas_sp_aasi --dry-run
```

Outputs:

- CSV: `places_full.csv` (same folder as input; or `output/places/cnpj_manual/` for `--cnpj` alone)
- Checkpoint: `places.cnpj.seen.json` (resume by `place_id`)

Extra columns include `razao_social`, `nome_fantasia`, `situacao`, `cnae`, `cnae_descricao`, `fiscal_*` (endereço fiscal + CEP), `natureza_juridica`, `porte`, `federal_phone_*`, `federal_email`, `qsa_nomes`, `qsa_qualificacoes`, `qsa_raw` (sócios da BrasilAPI), `cnpj_status`, `cnpj_status_reason`, `cnpj_scraped_at`. Does **not** overwrite website `email`.

**Smoke (manual):** `places.all --city … --state … --skip-llm` on a small BR city, or run stages ①→②→③; confirm name/phone/address, then e-mail when the site exposes contact, then `razao_social` / `situacao` when `cnpj_raw` is valid.

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
| `places.website` | Website crawl → enrich places.csv (e-mail) |
| `places.cnpj` | BrasilAPI CNPJ → enrich places_enriched.csv (federal) |
| `places.all` | One city: search → website → cnpj |

## Architecture

- `src/datascrapping/core/` — contract, registry, HTTP, browser helpers, sinks, checkpoint
- `src/datascrapping/scrapers/blog/` — blog crawlers
- `src/datascrapping/scrapers/bni/` — auth, search, profile, CSV orchestration
- `src/datascrapping/scrapers/places/` — Places search + website + CNPJ + `places.all` pipeline → CSV
- `src/datascrapping/cli.py` — Typer CLI

## Development

```bash
poetry run task lint
poetry run task test
```

## Deprecating scrap_auditik

All blog scraping scripts from `scrap_auditik` live here now. After validating this CLI, archive that repository on GitHub and point its README here.
