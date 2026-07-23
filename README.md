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
```

## Usage — blogs

```bash
poetry run datascrapping list
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

BNI directory search returns **at most ~250 results** per query. **`--specialty` is required** and must be a value from BNI’s **Search Category** dropdown (not free text). `--region` (State) is optional.

```bash
# Discover valid specialty labels (EN / pt_BR / es)
poetry run datascrapping bni-specialties
poetry run datascrapping bni-specialties --query fono --locale pt_BR
poetry run datascrapping bni-specialties -q hearing

# Minimum: specialty only (localized or English label both work)
poetry run datascrapping run bni --specialty "Fonoaudiologia"
poetry run datascrapping run bni --specialty "Hearing/Audiology"

# Safer cut with State + specialty
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

- CSV: `output/bni/<country>_<region|all>_<specialty>/members.csv`
- Checkpoint: `members.seen.json` (resume skips already collected profile URLs)
- Session: `output/.auth/bni_storage.json` (gitignored)

If BNI starts requiring 2FA/CAPTCHA, re-run with `--headed --reauth`, complete the challenge in the browser, then continue; the session is saved for later headless runs.

Use only with your own account and within BNI terms of use.

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

## Architecture

- `src/datascrapping/core/` — contract, registry, HTTP, browser helpers, sinks, checkpoint
- `src/datascrapping/scrapers/blog/` — blog crawlers
- `src/datascrapping/scrapers/bni/` — auth, search, profile, CSV orchestration
- `src/datascrapping/cli.py` — Typer CLI

## Development

```bash
poetry run task lint
poetry run task test
```

## Deprecating scrap_auditik

All blog scraping scripts from `scrap_auditik` live here now. After validating this CLI, archive that repository on GitHub and point its README here.
