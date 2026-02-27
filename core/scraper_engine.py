"""Core scraping engine: BFS crawler with httpx, retry, UA rotation, rate limiting."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random,
)

from core.config_manager import ScraperConfig, SiteConfig
from utils.helpers import RateLimiter, UserAgentRotator, build_headers, normalize_url
from utils.validators import clean_text, is_scrapeable_url, is_valid_url

logger = logging.getLogger("scrapeclaw.engine")
console = Console()


@dataclass
class ScrapedPage:
    """Result of scraping a single page."""

    url: str
    title: str | None = None
    html: str = ""
    text: str | None = None
    links: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status_code: int = 200
    error: str | None = None


class ScraperEngine:
    """
    BFS web crawler using httpx.Client.

    Pattern: to_fetch list + fetched set for deduplication.
    Features: tenacity retry, UA rotation, proxy support, rich progress.
    """

    def __init__(self, config: ScraperConfig, site: SiteConfig) -> None:
        self.config = config
        self.site = site
        self._ua_rotator = UserAgentRotator()
        self._rate_limiter = RateLimiter(site.rate_limit.delay_sec)

    def crawl(self) -> list[ScrapedPage]:
        """BFS crawl starting from site.start_url. Returns scraped pages."""
        pages: list[ScrapedPage] = []
        to_fetch: list[str] = [self.site.start_url]
        fetched: set[str] = set()

        proxy_map = self._build_proxy_map()

        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            proxy=proxy_map,
        ) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Crawling [bold]{self.site.name}[/]",
                    total=self.site.max_pages,
                )

                while to_fetch and len(fetched) < self.site.max_pages:
                    url = to_fetch.pop(0)
                    normalized = normalize_url(url)

                    if normalized in fetched:
                        continue
                    fetched.add(normalized)

                    self._rate_limiter.wait()

                    page = self._fetch_and_parse(client, url)
                    if page and not page.error:
                        pages.append(page)
                        # BFS: enqueue discovered links
                        for link in page.links:
                            link_norm = normalize_url(link)
                            if (
                                link_norm not in fetched
                                and link_norm not in {normalize_url(u) for u in to_fetch}
                                and self._is_allowed(link)
                                and is_scrapeable_url(link)
                            ):
                                to_fetch.append(link)
                    elif page:
                        # Record failed page for error reporting
                        pages.append(page)

                    progress.update(task, completed=len(fetched))

        successful = sum(1 for p in pages if not p.error)
        failed = sum(1 for p in pages if p.error)
        console.print(
            f"  Crawl complete: [green]{successful}[/] pages, "
            f"[red]{failed}[/] errors, "
            f"[dim]{len(fetched)}[/] URLs visited"
        )
        return pages

    def scrape_single(self, url: str) -> ScrapedPage:
        """Scrape a single URL (no crawling). Useful for one-off extraction."""
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            return self._fetch_and_parse(client, url) or ScrapedPage(
                url=url, error="Failed to fetch"
            )

    def _fetch_and_parse(self, client: httpx.Client, url: str) -> ScrapedPage | None:
        """Fetch URL, parse HTML, extract links. Falls back to Playwright if needed."""
        try:
            if self.site.js_required:
                return self._fetch_playwright(url)

            resp = self._fetch_url(client, url)
            if resp is None:
                return ScrapedPage(url=url, error="No response after retries")
            return self._parse_response(resp, url)

        except RetryError:
            logger.warning(f"All retries exhausted for {url}")
            return ScrapedPage(url=url, error="All retries exhausted")
        except Exception as exc:
            logger.warning(f"Failed to fetch {url}: {exc}")
            return ScrapedPage(url=url, error=str(exc))

    def _make_fetch_with_retry(self, config: ScraperConfig):
        """Create a retry-decorated fetch function with config-driven parameters."""

        @retry(
            stop=stop_after_attempt(config.rate_limit.max_retries),
            wait=wait_random(
                min=config.rate_limit.retry_wait_min,
                max=config.rate_limit.retry_wait_max,
            ),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _fetch(client: httpx.Client, url: str, headers: dict) -> httpx.Response:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp

        return _fetch

    def _fetch_url(self, client: httpx.Client, url: str) -> httpx.Response | None:
        """HTTP GET with rotating UA and tenacity retry."""
        ua = self._ua_rotator.get()
        extra = dict(self.site.custom_headers) if self.site.custom_headers else None
        headers = build_headers(ua, extra)

        fetch_fn = self._make_fetch_with_retry(self.config)
        return fetch_fn(client, url, headers)

    def _parse_response(self, resp: httpx.Response, url: str) -> ScrapedPage:
        """Parse HTTP response into ScrapedPage with BS4."""
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract title
        title_tag = soup.find("title")
        title = clean_text(title_tag.get_text()) if title_tag else None

        # Strip noise before text extraction
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        text = clean_text(soup.get_text(separator=" "))

        # Extract links for BFS
        links: list[str] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            full_url = urljoin(url, href)
            if is_valid_url(full_url):
                links.append(full_url)

        # Metadata
        meta_desc = soup.find("meta", attrs={"name": "description"})
        h1_tag = soup.find("h1")
        metadata = {
            "description": clean_text(meta_desc.get("content")) if meta_desc else None,
            "h1": clean_text(h1_tag.get_text()) if h1_tag else None,
        }

        return ScrapedPage(
            url=url,
            title=title,
            html=resp.text,
            text=text,
            links=links,
            metadata=metadata,
            status_code=resp.status_code,
        )

    def _is_allowed(self, url: str) -> bool:
        """Check URL is within allowed_domains."""
        try:
            domain = urlparse(url).netloc.lower()
            return any(
                domain == d or domain.endswith("." + d) for d in self.site.allowed_domains
            )
        except Exception:
            return False

    def _build_proxy_map(self) -> str | None:
        """Build proxy URL for httpx. Returns single proxy string or None."""
        if not self.config.proxy.enabled or not self.config.proxy.urls:
            return None
        return random.choice(self.config.proxy.urls)

    def _fetch_playwright(self, url: str) -> ScrapedPage | None:
        """Playwright fallback for JavaScript-heavy sites."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                ua = self._ua_rotator.get()
                page.set_extra_http_headers(build_headers(ua))
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()

            # Reuse BS4 parse logic with a mock response
            mock_resp = type("MockResponse", (), {"text": html, "status_code": 200})()
            return self._parse_response(mock_resp, url)

        except ImportError:
            logger.error(
                "Playwright not installed. Install with: pip install playwright && playwright install chromium"
            )
            return ScrapedPage(url=url, error="Playwright not installed")
        except Exception as exc:
            logger.error(f"Playwright fetch failed for {url}: {exc}")
            return ScrapedPage(url=url, error=f"Playwright: {exc}")
