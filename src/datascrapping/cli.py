from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from datascrapping import __version__
from datascrapping.cli_help import (
    BLOG_PAGINATION_MODES,
    BNI_CATEGORY_GROUPS,
    BNI_SPECIALTY_EXAMPLES,
    PLACES_EXAMPLES,
    PLACES_FLAGS,
    PLACES_PIPELINE,
    SHARED_DEFAULTS,
)
from datascrapping.core.base import ScrapeContext
from datascrapping.core.config import default_delays, default_output_dir, load_env
from datascrapping.core.registry import registry
from datascrapping.scrapers.loader import load_scrapers

APP_EPILOG = (
    "Commands to explore options:\n\n"
    "  datascrapping guide              Decision guide (blog / BNI / Places pipeline)\n"
    "  datascrapping list               Registered scrapers by family\n"
    "  datascrapping bni-specialties    Live BNI Search Category list (login)\n"
    "  datascrapping run --help         Flags: Shared / Blog / BNI / Places\n\n"
    "Places: places.all (search→website→cnpj) or stages alone — see guide §6"
)

app = typer.Typer(
    name="datascrapping",
    help=(
        "CLI toolkit for structured web scraping and data collection.\n\n"
        "Families: [bold]blog.*[/bold] (HTTP markdown), "
        "[bold]bni[/bold] (BNI Connect → CSV), "
        "[bold]places.*[/bold] (Google Places prospection → CSV; "
        "one-shot [cyan]places.all[/cyan] = search→website→cnpj)."
    ),
    epilog=APP_EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _print_guide() -> None:
    console.print(
        Panel.fit(
            Text.from_markup(
                f"[bold]datascrapping {__version__}[/bold] — how to choose "
                "and run scrapers"
            ),
            border_style="cyan",
        )
    )

    console.print("\n[bold cyan]1. Pick a family[/bold cyan]")
    family = Table(show_header=True, header_style="bold")
    family.add_column("Family")
    family.add_column("Scrapers")
    family.add_column("Typical goal")
    family.add_row(
        "Blog",
        "blog.auditik, blog.communicare, blog.essencial,\n"
        "blog.otoclinic, blog.sonorita, blog.concorrente, blog.all",
        "Crawl listing pages → save article markdown",
    )
    family.add_row(
        "BNI",
        "bni",
        "Search BNI Connect members → CSV "
        "(login via BNI_EMAIL / BNI_PASSWORD)",
    )
    family.add_row(
        "Places",
        "places.search → places.website → places.cnpj\n"
        "(or places.all for all three)",
        "3-stage prospection: Google Places → website crawl → "
        "BrasilAPI CNPJ (GOOGLE_PLACES_API_KEY for stage 1)",
    )
    console.print(family)

    console.print("\n[bold cyan]2. Shared flags[/bold cyan] (all families)")
    shared = Table(show_header=True, header_style="bold")
    shared.add_column("Flag / setting")
    shared.add_column("Default / notes")
    for name, note in SHARED_DEFAULTS:
        shared.add_row(name, note)
    shared.add_row("--dry-run", "Discover/extract without writing files")
    shared.add_row("-v / --verbose", "Debug logging")
    console.print(shared)

    console.print("\n[bold magenta]3. Blog scrapers[/bold magenta]")
    console.print(
        "Use [cyan]datascrapping list[/cyan] then:\n"
        "  [green]datascrapping run blog.auditik[/green]\n"
        "  [green]datascrapping run blog.concorrente "
        "--url https://site.com/blog/ --out pasta[/green]\n"
        "  [green]datascrapping run blog.all --delay-min 1.5 "
        "--delay-max 4[/green]"
    )
    blog_flags = Table(title="Blog-only flags", show_header=True)
    blog_flags.add_column("Flag")
    blog_flags.add_column("Purpose")
    blog_flags.add_row(
        "--url", "Listing URL (required for blog.concorrente)"
    )
    blog_flags.add_row(
        "--out", "Output subdirectory name under --out-dir"
    )
    blog_flags.add_row(
        "--pagination",
        "auto | simple | numbered | bfs",
    )
    blog_flags.add_row(
        "--max-pages",
        "Cap listing pages for auto/bfs (optional)",
    )
    console.print(blog_flags)

    modes = Table(title="--pagination values", show_header=True)
    modes.add_column("Mode", style="cyan")
    modes.add_column("Meaning")
    for mode, meaning in BLOG_PAGINATION_MODES:
        modes.add_row(mode, meaning)
    console.print(modes)

    console.print("\n[bold yellow]4. BNI scraper[/bold yellow]")
    console.print(
        "Needs Poetry extra [cyan]browser[/cyan] + Playwright Chromium "
        "and credentials in [cyan].env[/cyan] "
        "([cyan]BNI_EMAIL[/cyan] / [cyan]BNI_PASSWORD[/cyan]).\n"
        "All search filters are optional; omit any you do not need.\n"
        "BNI caps directory search at ~[bold]250[/bold] results — "
        "narrow with --specialty / --region when possible."
    )
    bni_flags = Table(title="BNI-only flags", show_header=True)
    bni_flags.add_column("Flag")
    bni_flags.add_column("Purpose / known values")
    bni_flags.add_row(
        "--country",
        "Geographic country (default: Brazil). Example: Brazil",
    )
    bni_flags.add_row(
        "--region",
        "State / UF free text (e.g. SP, MG, Rio de Janeiro)",
    )
    bni_flags.add_row(
        "--locale",
        "Language for BNI API/labels: en | pt_BR | es "
        "(not geography — use --country/--region for place)",
    )
    bni_flags.add_row(
        "--specialty",
        "Search Category from BNI's fixed list — "
        "not free text. See examples below and "
        "[cyan]bni-specialties[/cyan]",
    )
    bni_flags.add_row(
        "--category",
        "Primary group filter alone (e.g. Health & Wellness) "
        "or hint with --specialty. See groups below / "
        "[cyan]bni-specialties --groups-only[/cyan].",
    )
    bni_flags.add_row(
        "--all-pages",
        "Walk every API results page for the cut (slower)",
    )
    bni_flags.add_row(
        "--headed",
        "Show browser (needed for 2FA/CAPTCHA)",
    )
    bni_flags.add_row(
        "--reauth",
        "Ignore saved session; log in again",
    )
    console.print(bni_flags)

    examples = Table(
        title="Example --specialty values (EN ↔ pt_BR)",
        show_header=True,
    )
    examples.add_column("English (UI)", style="cyan")
    examples.add_column("pt_BR")
    examples.add_column("Group")
    for en, pt, group in BNI_SPECIALTY_EXAMPLES:
        examples.add_row(en, pt, group)
    console.print(examples)
    console.print(
        "[dim]Either label works with --specialty; the scraper maps "
        "locales via BNI's category id.[/dim]"
    )

    groups = Table(
        title=f"Known BNI --category groups ({len(BNI_CATEGORY_GROUPS)})",
        show_header=False,
    )
    groups.add_column("Group")
    # 2-column layout via paired rows
    items = list(BNI_CATEGORY_GROUPS)
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if i + 1 < len(items) else ""
        groups.add_row(f"{left}" + (f"    |    {right}" if right else ""))
    console.print(groups)
    console.print(
        "Live specialty list (login required):\n"
        "  [green]datascrapping bni-specialties[/green]\n"
        "  [green]datascrapping bni-specialties -q fono --locale pt_BR[/green]\n"
        "  [green]datascrapping bni-specialties -q hearing[/green]"
    )

    console.print("\n[bold cyan]5. Example BNI runs[/bold cyan]")
    console.print(
        "  [green]datascrapping run bni[/green]\n"
        "  [green]datascrapping run bni --region SP[/green]\n"
        "  [green]datascrapping run bni --specialty Fonoaudiologia[/green]\n"
        "  [green]datascrapping run bni --category \"Health & Wellness\" "
        "--locale pt_BR --all-pages[/green]\n"
        "  [green]datascrapping run bni --region SP "
        "--specialty \"Hearing/Audiology\" --all-pages[/green]\n"
        "  [green]datascrapping run bni --headed --reauth[/green]"
    )

    console.print("\n[bold green]6. Places scrapers[/bold green] (run in order)")
    console.print(
        "Always use [cyan]datascrapping run <scraper>[/cyan] "
        "(not [red]datascrapping places.search[/red]).\n"
        "Recommended for a new city: "
        "[cyan]places.all[/cyan] (runs stages 1→2→3).\n"
        "Slug folder: [cyan]output/places/<city>_<uf>_<niche>/[/cyan] "
        "(e.g. [cyan]campinas_sp_aasi[/cyan]). "
        "With separate stages, pass [cyan]--from[/cyan] as that folder "
        "or the CSV file inside it.\n"
        "CEP / endereço fiscal vêm da BrasilAPI CNPJ (stage 3), não de ViaCEP.\n"
        "Stage 2 also extracts [cyan]whatsapp[/cyan] and best-effort social bios "
        "(HTTP only; IG/FB/LinkedIn often login-wall). "
        "Stage 3 adds [cyan]qsa_*[/cyan] (sócios)."
    )
    pipeline = Table(
        title="Places pipeline (one city end-to-end)",
        show_header=True,
        header_style="bold",
    )
    pipeline.add_column("Stage", style="cyan", justify="center")
    pipeline.add_column("Scraper")
    pipeline.add_column("Input")
    pipeline.add_column("Output")
    pipeline.add_column("Env / notes")
    for stage, scraper, inp, out, env_note in PLACES_PIPELINE:
        pipeline.add_row(stage, scraper, inp, out, env_note)
    console.print(pipeline)

    places_flags = Table(
        title="Places flags (which scraper uses each)",
        show_header=True,
    )
    places_flags.add_column("Flag")
    places_flags.add_column("Used by / purpose")
    for flag, purpose in PLACES_FLAGS:
        places_flags.add_row(flag, purpose)
    console.print(places_flags)

    console.print(
        "\n[bold]Full city recipe[/bold] — one command "
        "([cyan]places.all[/cyan]):\n"
        '  [green]datascrapping run places.all --city "Campinas" '
        "--state SP --skip-llm[/green]\n"
        "Or step by step:\n"
        '  [green]datascrapping run places.search --city "Campinas" '
        "--state SP[/green]\n"
        "  [green]datascrapping run places.website "
        "--from output/places/campinas_sp_aasi --skip-llm[/green]\n"
        "  [green]datascrapping run places.cnpj "
        "--from output/places/campinas_sp_aasi[/green]\n"
        "[cyan]places.all[/cyan] uses the same flags as search "
        "([cyan]--city/--state/--niche/--max-quota/--skip-geo-check[/cyan]) "
        "plus [cyan]--skip-llm[/cyan] for stage 2; "
        "[cyan]--from[/cyan] is computed from the city slug.\n"
        "Resume: re-run the same stage or [cyan]places.all[/cyan]; "
        "checkpoints skip already-saved [cyan]place_id[/cyan]s.\n"
        "Optional Gemini on stage 2: omit [cyan]--skip-llm[/cyan] after "
        "[cyan]poetry install -E llm[/cyan] and set [cyan]GEMINI_API_KEY[/cyan]."
    )

    places_ex = Table(title="More Places examples", show_header=True)
    places_ex.add_column("Command", style="green")
    places_ex.add_column("Notes")
    for cmd, note in PLACES_EXAMPLES:
        places_ex.add_row(f"datascrapping {cmd}", note)
    console.print(places_ex)

    console.print(
        "\n[dim]Tip: [cyan]datascrapping run --help[/cyan] shows Shared / Blog / "
        "BNI / Places panels. Prefer [cyan]datascrapping guide[/cyan] for the "
        "Places pipeline order.[/dim]"
    )


@app.callback()
def main(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug logging."
    ),
) -> None:
    """Datascrapping CLI."""
    load_env()
    load_scrapers()
    _setup_logging(verbose)


@app.command("guide")
def show_guide() -> None:
    """Show a decision guide: blog / BNI / Places pipeline (incl. places.all)."""
    _print_guide()


@app.command("list")
def list_scrapers() -> None:
    """List registered scrapers grouped by family (blog / BNI / Places)."""
    entries = registry.list()
    blog = [(n, d) for n, d in entries if n.startswith("blog.")]
    bni = [(n, d) for n, d in entries if n == "bni" or n.startswith("bni.")]
    places = [(n, d) for n, d in entries if n.startswith("places.")]
    other = [
        (n, d)
        for n, d in entries
        if not n.startswith("blog.")
        and n != "bni"
        and not n.startswith("bni.")
        and not n.startswith("places.")
    ]

    def _table(title: str, rows: list[tuple[str, str]]) -> None:
        if not rows:
            return
        table = Table(title=title)
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        for name, description in rows:
            table.add_row(name, description)
        console.print(table)

    console.print(
        Panel.fit(
            f"datascrapping {__version__} — scrapers",
            border_style="cyan",
        )
    )
    _table("Blog scrapers", blog)
    _table("BNI scrapers", bni)
    _table("Places scrapers", places)
    _table("Other scrapers", other)
    console.print(
        "\n[dim]How to choose flags:[/dim] [cyan]datascrapping guide[/cyan]\n"
        "[dim]Places one-shot:[/dim] [cyan]datascrapping run places.all "
        '--city "…" --state UF --skip-llm[/cyan]\n'
        "[dim]BNI specialties:[/dim] [cyan]datascrapping bni-specialties[/cyan]"
    )


@app.command(
    "run",
    epilog=(
        "See also: [cyan]datascrapping guide[/cyan] §6 Places · "
        "[cyan]datascrapping list[/cyan] · "
        "[cyan]datascrapping run places.all --help[/cyan] "
        "(same flags; pipeline: search→website→cnpj)"
    ),
)
def run_scraper(
    scraper: str = typer.Argument(
        ...,
        help=(
            "Scraper from [cyan]list[/cyan]: blog.* / bni / "
            "places.search|website|cnpj|[bold]all[/bold]."
        ),
        rich_help_panel="Target",
    ),
    # Shared
    out: Optional[str] = typer.Option(
        None,
        "--out",
        help="Output subdirectory under --out-dir (mostly blog).",
        rich_help_panel="Shared",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        help="Root output directory (default: OUTPUT_DIR or ./output).",
        rich_help_panel="Shared",
    ),
    delay_min: Optional[float] = typer.Option(
        None,
        "--delay-min",
        help="Minimum delay between requests/profiles.",
        rich_help_panel="Shared",
    ),
    delay_max: Optional[float] = typer.Option(
        None,
        "--delay-max",
        help="Maximum delay between requests/profiles.",
        rich_help_panel="Shared",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Discover/extract without writing files. "
            "places.all: validate flags + print planned stages only."
        ),
        rich_help_panel="Shared",
    ),
    # Blog
    url: Optional[str] = typer.Option(
        None,
        "--url",
        help="Listing URL (required by blog.concorrente).",
        rich_help_panel="Blog scrapers",
    ),
    pagination: Optional[str] = typer.Option(
        None,
        "--pagination",
        help="Pagination mode: auto|simple|numbered|bfs (default auto).",
        rich_help_panel="Blog scrapers",
    ),
    max_pages: Optional[int] = typer.Option(
        None,
        "--max-pages",
        help="Max listing pages to crawl (auto/bfs).",
        rich_help_panel="Blog scrapers",
    ),
    # BNI
    country: Optional[str] = typer.Option(
        None,
        "--country",
        help="Geographic country filter (default: Brazil). Example: Brazil.",
        rich_help_panel="BNI scraper",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="State/UF filter (optional free text, e.g. SP).",
        rich_help_panel="BNI scraper",
    ),
    locale: Optional[str] = typer.Option(
        None,
        "--locale",
        help=(
            "BNI language locale for API/labels: en, pt_BR, or es "
            "(aliases: pt, en-US, es-ES). Default: session locale. "
            "Not the same as --country."
        ),
        rich_help_panel="BNI scraper",
    ),
    specialty: Optional[str] = typer.Option(
        None,
        "--specialty",
        help=(
            "Search Category from BNI's known list (optional, not free text). "
            "Examples: Hearing/Audiology, Fonoaudiologia. "
            "List all: [cyan]bni-specialties[/cyan]."
        ),
        rich_help_panel="BNI scraper",
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        help=(
            "Primary category group (optional), e.g. Health & Wellness. "
            "BNI's API only filters by specialty, so --category expands into "
            "one search per specialty in the group. See [cyan]guide[/cyan] / "
            "[cyan]bni-specialties --groups-only[/cyan]."
        ),
        rich_help_panel="BNI scraper",
    ),
    all_pages: bool = typer.Option(
        False,
        "--all-pages",
        help="Walk every results page for the filter cut (slower).",
        rich_help_panel="BNI scraper",
    ),
    headed: bool = typer.Option(
        False,
        "--headed",
        help="Show the browser (also used for 2FA/CAPTCHA).",
        rich_help_panel="BNI scraper",
    ),
    reauth: bool = typer.Option(
        False,
        "--reauth",
        help="Ignore saved session and log in again.",
        rich_help_panel="BNI scraper",
    ),
    # Places (pipeline: search → website → cnpj; see datascrapping guide)
    city: Optional[str] = typer.Option(
        None,
        "--city",
        help="① places.search / places.all (required). City name, e.g. Campinas.",
        rich_help_panel="Places scrapers",
    ),
    state: Optional[str] = typer.Option(
        None,
        "--state",
        help="① places.search / places.all (required). UF 2 letters, e.g. SP.",
        rich_help_panel="Places scrapers",
    ),
    niche: Optional[str] = typer.Option(
        None,
        "--niche",
        help="① places.search / places.all. terms.json key (default: aasi).",
        rich_help_panel="Places scrapers",
    ),
    skip_geo_check: bool = typer.Option(
        False,
        "--skip-geo-check",
        help="① places.search / places.all. Skip BrasilAPI IBGE city/UF check.",
        rich_help_panel="Places scrapers",
    ),
    max_quota: Optional[int] = typer.Option(
        None,
        "--max-quota",
        help="① places.search / places.all. Max Places quota units (default: 20000).",
        rich_help_panel="Places scrapers",
    ),
    from_path: Optional[str] = typer.Option(
        None,
        "--from",
        help=(
            "② website: places.csv or folder; "
            "③ cnpj: places_enriched.csv or folder. "
            "(Not needed for places.all.)"
        ),
        rich_help_panel="Places scrapers",
    ),
    skip_llm: bool = typer.Option(
        False,
        "--skip-llm",
        help="② places.website / places.all. Heuristics only (no Gemini).",
        rich_help_panel="Places scrapers",
    ),
    cnpj: Optional[str] = typer.Option(
        None,
        "--cnpj",
        help="③ places.cnpj only. Smoke one CNPJ (or filter with --from).",
        rich_help_panel="Places scrapers",
    ),
) -> None:
    """Run a registered scraper.

    [bold]Places[/bold] pipeline: [cyan]places.search[/cyan] →
    [cyan]places.website[/cyan] → [cyan]places.cnpj[/cyan], or one-shot
    [cyan]places.all[/cyan]. See [cyan]datascrapping guide[/cyan] §6.
    Flags differ by family — panels below (①/②/③ mark Places stage).
    """
    env_min, env_max = default_delays()
    delay_explicit = delay_min is not None or delay_max is not None
    extras = {
        key: value
        for key, value in {
            "url": url,
            "out": out,
            "country": country,
            "region": region,
            "locale": locale,
            "specialty": specialty,
            "category": category,
            "pagination": pagination,
            "max_pages": max_pages,
            "city": city,
            "state": state,
            "niche": niche,
            "max_quota": max_quota,
            "from_path": from_path,
            "cnpj": cnpj,
        }.items()
        if value is not None
    }
    if all_pages:
        extras["all_pages"] = True
    if headed:
        extras["headed"] = True
    if reauth:
        extras["reauth"] = True
    if skip_geo_check:
        extras["skip_geo_check"] = True
    if skip_llm:
        extras["skip_llm"] = True
    if delay_explicit:
        extras["delay_explicit"] = True

    ctx = ScrapeContext(
        out_dir=(out_dir or default_output_dir()).resolve(),
        delay_min=delay_min if delay_min is not None else env_min,
        delay_max=delay_max if delay_max is not None else env_max,
        dry_run=dry_run,
        extras=extras,
    )

    try:
        scraper_cls = registry.get(scraper)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print(
            "[dim]Try[/dim] [cyan]datascrapping list[/cyan] "
            "[dim]or[/dim] [cyan]datascrapping guide[/cyan]"
        )
        raise typer.Exit(code=1) from exc

    console.print(
        f"[bold]Running[/bold] {scraper} → {ctx.out_dir}"
        + (" [yellow](dry-run)[/yellow]" if dry_run else "")
    )
    try:
        result = scraper_cls().run(ctx)
    except NotImplementedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        console.print(f"[red]Scraper failed: {exc}[/red]")
        logging.exception("Scraper crashed")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Done.[/green] saved={result.saved} "
        f"skipped={result.skipped} errors={result.errors}"
    )
    if result.output_path:
        console.print(f"Output: {result.output_path}")
    if result.message:
        console.print(result.message)


@app.command("bni-specialties")
def bni_specialties(
    query: Optional[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="Filter specialties by substring (any locale label).",
    ),
    locale: str = typer.Option(
        "en",
        "--locale",
        "-l",
        help="Display locale: en, pt_BR, or es.",
    ),
    groups_only: bool = typer.Option(
        False,
        "--groups-only",
        help="Only print primary category groups (no login / network).",
    ),
    headed: bool = typer.Option(
        False, "--headed", help="Show browser while authenticating."
    ),
    reauth: bool = typer.Option(
        False, "--reauth", help="Ignore saved session and log in again."
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        help="Root output directory (default: OUTPUT_DIR or ./output).",
    ),
) -> None:
    """List BNI Search Category values for --specialty.

    Without network: [cyan]--groups-only[/cyan] shows known primary groups.
    Full specialty list requires a logged-in BNI session.
    """
    if groups_only:
        table = Table(
            title=f"BNI primary category groups ({len(BNI_CATEGORY_GROUPS)})"
        )
        table.add_column("#", style="dim")
        table.add_column("Group (--category)", style="cyan")
        for index, group in enumerate(BNI_CATEGORY_GROUPS, start=1):
            table.add_row(str(index), group)
        console.print(table)
        console.print(
            "[dim]Full specialty labels:[/dim] "
            "[cyan]datascrapping bni-specialties[/cyan] "
            "[dim](or[/dim] [cyan]-q …[/cyan][dim]). "
            "Examples in[/dim] [cyan]datascrapping guide[/cyan]."
        )
        return

    from datascrapping.core.browser import BrowserUnavailableError, browser_session
    from datascrapping.scrapers.bni.auth import ensure_authenticated
    from datascrapping.scrapers.bni.categories import (
        UI_LOCALE,
        fetch_categories,
        find_category_matches,
    )

    root = (out_dir or default_output_dir()).resolve()
    storage_path = root / ".auth" / "bni_storage.json"

    try:
        with browser_session(
            headed=headed,
            storage_state=None if reauth else storage_path,
        ) as (_pw, _browser, context, page):
            ensure_authenticated(
                page,
                context,
                storage_path=storage_path,
                headed=headed,
                reauth=reauth,
            )
            page.goto(
                "https://www.bniconnectglobal.com/web/",
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(800)
            display = fetch_categories(context, locale=locale)
            english = (
                display
                if locale == UI_LOCALE
                else fetch_categories(context, locale=UI_LOCALE)
            )
    except BrowserUnavailableError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Failed to list BNI specialties: {exc}[/red]")
        logging.exception("bni-specialties failed")
        raise typer.Exit(code=1) from exc

    en_by_id = {c.secondary_id: c for c in english}
    rows = display
    if query:
        matched_ids = {
            c.secondary_id
            for c in find_category_matches(query, display, limit=500)
        }
        if locale != UI_LOCALE:
            matched_ids.update(
                c.secondary_id
                for c in find_category_matches(query, english, limit=500)
            )
        rows = [c for c in display if c.secondary_id in matched_ids]
        if not rows:
            console.print(
                f"[yellow]No specialties matched[/yellow] {query!r}. "
                "Try a broader --query or locale en/pt_BR/es."
            )
            raise typer.Exit(code=1)

    table = Table(title=f"BNI Search Categories ({locale}) — {len(rows)}")
    table.add_column("Specialty (--specialty)", style="cyan")
    table.add_column("Group (--category)")
    if locale != UI_LOCALE:
        table.add_column("English UI value")
    for category in sorted(rows, key=lambda c: (c.primary, c.secondary)):
        values = [category.secondary, category.primary]
        if locale != UI_LOCALE:
            en = en_by_id.get(category.secondary_id)
            values.append(en.secondary if en else "")
        table.add_row(*values)
    console.print(table)
    console.print(
        "[dim]Use either the localized or English label with "
        "--specialty; the scraper maps them automatically.[/dim]\n"
        "[dim]Decision guide:[/dim] [cyan]datascrapping guide[/cyan]"
    )


if __name__ == "__main__":
    app()
