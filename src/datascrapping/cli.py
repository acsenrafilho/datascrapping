from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from datascrapping import __version__
from datascrapping.core.base import ScrapeContext
from datascrapping.core.config import default_delays, default_output_dir, load_env
from datascrapping.core.registry import registry
from datascrapping.scrapers.loader import load_scrapers

app = typer.Typer(
    name="datascrapping",
    help="CLI toolkit for structured web scraping and data collection.",
    no_args_is_help=True,
    add_completion=False,
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


@app.command("list")
def list_scrapers() -> None:
    """List registered scrapers."""
    table = Table(title=f"datascrapping {__version__} — scrapers")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for name, description in registry.list():
        table.add_row(name, description)
    console.print(table)


@app.command("run")
def run_scraper(
    scraper: str = typer.Argument(..., help="Scraper name (see `list`)."),
    url: Optional[str] = typer.Option(
        None, "--url", help="Listing URL (required by blog.concorrente)."
    ),
    out: Optional[str] = typer.Option(
        None, "--out", help="Output subdirectory under --out-dir."
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        help="Root output directory (default: OUTPUT_DIR or ./output).",
    ),
    delay_min: Optional[float] = typer.Option(
        None, "--delay-min", help="Minimum delay between requests/profiles."
    ),
    delay_max: Optional[float] = typer.Option(
        None, "--delay-max", help="Maximum delay between requests/profiles."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Discover/extract without writing files."
    ),
    country: Optional[str] = typer.Option(
        None, "--country", help="BNI country filter (default: Brazil)."
    ),
    region: Optional[str] = typer.Option(
        None, "--region", help="BNI Estado/UF filter (optional)."
    ),
    specialty: Optional[str] = typer.Option(
        None,
        "--specialty",
        help=(
            "BNI Search Category (required for bni). "
            "Use English or localized labels; see `bni-specialties`."
        ),
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        help="BNI optional primary category group (e.g. Health & Wellness).",
    ),
    all_pages: bool = typer.Option(
        False,
        "--all-pages",
        help=(
            "BNI: walk every results page for the filtered search "
            "(slower; use consciously)."
        ),
    ),
    headed: bool = typer.Option(
        False,
        "--headed",
        help="BNI: show the browser (also used for 2FA/CAPTCHA).",
    ),
    reauth: bool = typer.Option(
        False,
        "--reauth",
        help="BNI: ignore saved session and log in again.",
    ),
    pagination: Optional[str] = typer.Option(
        None,
        "--pagination",
        help="Blog: pagination mode auto|simple|numbered|bfs.",
    ),
    max_pages: Optional[int] = typer.Option(
        None,
        "--max-pages",
        help="Blog: max listing pages to crawl (auto/bfs).",
    ),
) -> None:
    """Run a registered scraper."""
    env_min, env_max = default_delays()
    delay_explicit = delay_min is not None or delay_max is not None
    extras = {
        key: value
        for key, value in {
            "url": url,
            "out": out,
            "country": country,
            "region": region,
            "specialty": specialty,
            "category": category,
            "pagination": pagination,
            "max_pages": max_pages,
        }.items()
        if value is not None
    }
    if all_pages:
        extras["all_pages"] = True
    if headed:
        extras["headed"] = True
    if reauth:
        extras["reauth"] = True
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
        raise typer.Exit(code=1) from exc

    if scraper == "bni":
        if not specialty:
            console.print(
                "[red]BNI requires --specialty (Search Category dropdown). "
                "List valid values with:[/red] "
                "[cyan]datascrapping bni-specialties[/cyan]\n"
                "[dim]--region (State) is optional.[/dim]"
            )
            raise typer.Exit(code=1)

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
    """List BNI Search Category values usable with --specialty."""
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
            # Ensure API cookies are established on the BNI origin.
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
        # Also match against English labels when displaying another locale.
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
    table.add_column("Group")
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
        "--specialty; the scraper maps them automatically.[/dim]"
    )


if __name__ == "__main__":
    app()
