"""ScrapeClaw — Enterprise web scraper with Claude AI extraction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="scrapeclaw",
    help="Enterprise web scraper with Claude AI extraction and Excel output.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _setup_logging(level: str) -> None:
    """Configure rich console + file logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    # File handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(
        log_dir / f"scrapeclaw_{datetime.now().strftime('%Y%m%d')}.log",
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(fh)


def _print_banner() -> None:
    console.print(
        Panel.fit(
            "[bold blue]ScrapeClaw[/bold blue] [dim]— Enterprise Web Scraper[/dim]\n"
            "[dim]AI-powered extraction with beautiful Excel output[/dim]",
            border_style="blue",
        )
    )


@app.command("scrape")
def scrape(
    site: str = typer.Argument(..., help="Site name from config/sites/<name>.yaml"),
    url: str = typer.Option(None, "--url", "-u", help="Override start URL from config"),
    max_pages: int = typer.Option(None, "--max-pages", "-p", help="Override max pages"),
    max_entries: int = typer.Option(None, "--max-entries", "-n", help="Override max entries"),
    playwright: bool = typer.Option(False, "--playwright", help="Force Playwright rendering"),
    no_claude: bool = typer.Option(False, "--no-claude", help="Skip Claude extraction"),
    output: str = typer.Option(None, "--output", "-o", help="Output Excel path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Crawl only, no extraction or output"),
    json_dump: bool = typer.Option(False, "--json", help="Also save raw data as JSON"),
) -> None:
    """
    Crawl a site and extract structured data with Claude AI.

    Examples:
      python main.py scrape example
      python main.py scrape example --max-pages 5 --dry-run
      python main.py scrape mysite --url https://example.com --no-claude
    """
    from core.config_manager import ConfigManager
    from core.scraper_engine import ScraperEngine

    _print_banner()

    cfg_mgr = ConfigManager()
    global_cfg = cfg_mgr.load_global()
    _setup_logging(global_cfg.log_level)

    try:
        site_cfg = cfg_mgr.load_site(site)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # CLI overrides
    if url:
        site_cfg.start_url = url
    if max_pages is not None:
        site_cfg.max_pages = max_pages
    if max_entries is not None:
        site_cfg.max_entries = max_entries
    if playwright:
        site_cfg.js_required = True

    console.print(f"  Target: [green]{site_cfg.start_url}[/green]")
    console.print(f"  Max pages: [cyan]{site_cfg.max_pages}[/cyan] | Max entries: [cyan]{site_cfg.max_entries}[/cyan]")
    console.print()

    # Phase 1: Crawl
    engine = ScraperEngine(global_cfg, site_cfg)
    pages = engine.crawl()
    console.print()

    if dry_run:
        console.print("[yellow]Dry run complete — no extraction or output.[/yellow]")
        # Show sample of crawled pages
        table = Table(title="Crawled Pages (sample)")
        table.add_column("URL", style="cyan", max_width=80)
        table.add_column("Title", max_width=40)
        table.add_column("Status", justify="center")
        for p in pages[:20]:
            status = "[green]OK[/green]" if not p.error else f"[red]{p.error[:30]}[/red]"
            table.add_row(p.url, p.title or "—", status)
        console.print(table)
        return

    # Phase 2: Claude Extraction
    results = []
    if no_claude or not site_cfg.extraction:
        if not site_cfg.extraction:
            console.print("[yellow]No extraction schema defined in site config. Skipping Claude.[/yellow]")
        else:
            console.print("[yellow]Claude extraction skipped (--no-claude).[/yellow]")

        # Create basic results from page data
        from core.claude_processor import ExtractionResult

        for p in pages:
            results.append(
                ExtractionResult(
                    url=p.url,
                    data={"title": p.title, "h1": p.metadata.get("h1"), "description": p.metadata.get("description")},
                    error=p.error,
                )
            )
    else:
        from core.claude_processor import ClaudeProcessor

        try:
            processor = ClaudeProcessor(global_cfg)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        console.print()
        results = processor.extract_batch(pages, site_cfg.extraction)

    console.print()

    # Phase 3: Excel Output
    from core.excel_formatter import ExcelFormatter

    out_dir = Path(global_cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(output) if output else out_dir / f"{site}_{timestamp}.xlsx"

    run_metadata = {
        "Site Config": site,
        "Start URL": site_cfg.start_url,
        "Max Pages": site_cfg.max_pages,
        "Max Entries": site_cfg.max_entries,
        "Claude Model": global_cfg.claude_model,
        "Claude Enabled": not no_claude,
        "JS Rendering": site_cfg.js_required,
    }

    formatter = ExcelFormatter(global_cfg.excel_theme)
    formatter.generate(results, site_name=site_cfg.name, output_path=out_path, run_metadata=run_metadata)

    # Optional JSON dump
    if json_dump:
        json_path = out_path.with_suffix(".json")
        json_data = [
            {"url": r.url, "data": r.data, "error": r.error, "tokens": r.tokens_used}
            for r in results
        ]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        console.print(f"  JSON saved: [underline]{json_path}[/underline]")

    console.print(f"\n  [bold green]Done![/bold green] Excel report: [underline]{out_path}[/underline]")


@app.command("scrape-url")
def scrape_url(
    url: str = typer.Argument(..., help="URL to scrape"),
    output: str = typer.Option(None, "--output", "-o", help="Output Excel path"),
    no_claude: bool = typer.Option(False, "--no-claude", help="Skip Claude extraction"),
    fields: str = typer.Option(
        None,
        "--fields",
        "-f",
        help="Comma-separated fields to extract (e.g. 'title,price,description')",
    ),
) -> None:
    """
    Scrape a single URL without a site config.

    Examples:
      python main.py scrape-url https://example.com
      python main.py scrape-url https://example.com -f "title,price,rating"
    """
    from urllib.parse import urlparse

    from core.claude_processor import ClaudeProcessor, ExtractionResult
    from core.config_manager import ConfigManager, ExtractionSchema, SiteConfig
    from core.excel_formatter import ExcelFormatter
    from core.scraper_engine import ScraperEngine

    _print_banner()

    cfg_mgr = ConfigManager()
    global_cfg = cfg_mgr.load_global()
    _setup_logging(global_cfg.log_level)

    domain = urlparse(url).netloc
    site_cfg = SiteConfig(
        name=domain,
        base_url=url,
        start_url=url,
        allowed_domains=[domain],
        max_pages=1,
        max_entries=1,
    )

    # Build extraction schema from --fields
    extraction = None
    if fields and not no_claude:
        field_dict = {f.strip(): f"Extract the {f.strip()}" for f in fields.split(",")}
        extraction = ExtractionSchema(fields=field_dict)
        site_cfg.extraction = extraction

    console.print(f"  Scraping: [green]{url}[/green]")
    console.print()

    engine = ScraperEngine(global_cfg, site_cfg)
    page = engine.scrape_single(url)

    if extraction and not no_claude:
        try:
            processor = ClaudeProcessor(global_cfg)
            results = processor.extract(page, extraction)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        results = [
            ExtractionResult(
                url=page.url,
                data={"title": page.title, "h1": page.metadata.get("h1"), "description": page.metadata.get("description")},
                error=page.error,
            )
        ]

    out_dir = Path(global_cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(output) if output else out_dir / f"single_{timestamp}.xlsx"

    formatter = ExcelFormatter(global_cfg.excel_theme)
    formatter.generate(results, site_name=domain, output_path=out_path)
    console.print(f"\n  [bold green]Done![/bold green] Output: [underline]{out_path}[/underline]")


@app.command("init-config")
def init_config(
    site: str = typer.Argument(..., help="Name for the new site config"),
    url: str = typer.Argument(..., help="Base URL to scrape"),
) -> None:
    """
    Generate a site config template.

    Example:
      python main.py init-config mysite https://example.com/listings
    """
    from core.config_manager import ConfigManager

    _print_banner()
    path = ConfigManager().create_site_template(site, url)
    console.print(f"  [green]Created:[/green] {path}")
    console.print(f"  Edit the YAML file to customize extraction fields, then run:")
    console.print(f"  [cyan]python main.py scrape {site}[/cyan]")


@app.command("list-configs")
def list_configs() -> None:
    """List all available site configurations."""
    from core.config_manager import ConfigManager

    _print_banner()
    sites = ConfigManager().list_sites()
    if not sites:
        console.print("  [yellow]No site configs found.[/yellow] Create one with:")
        console.print("  [cyan]python main.py init-config <name> <url>[/cyan]")
        return

    table = Table(title=f"Site Configurations ({len(sites)})")
    table.add_column("Name", style="cyan")
    table.add_column("Config Path", style="dim")

    for site_name in sites:
        table.add_row(site_name, f"config/sites/{site_name}.yaml")

    console.print(table)


@app.command("list-results")
def list_results(
    limit: int = typer.Option(20, "--limit", "-n", help="Max results to show"),
) -> None:
    """List recent output files."""
    _print_banner()
    out_dir = Path("output")
    if not out_dir.exists():
        console.print("  [yellow]No output directory yet.[/yellow] Run a scrape first.")
        return

    files = sorted(out_dir.glob("*.*"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        console.print("  [yellow]No output files found.[/yellow]")
        return

    table = Table(title=f"Recent Outputs (showing {min(limit, len(files))})")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Created", style="dim")

    for f in files[:limit]:
        size = f.stat().st_size
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size // 1024} KB"
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(f.name, size_str, mtime)

    console.print(table)


if __name__ == "__main__":
    app()
