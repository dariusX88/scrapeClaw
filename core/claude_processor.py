"""Claude AI processor: intelligent data extraction from scraped HTML."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.config_manager import ExtractionSchema, ScraperConfig
from core.scraper_engine import ScrapedPage
from utils.validators import truncate_html

logger = logging.getLogger("scrapeclaw.claude")
console = Console()


@dataclass
class ExtractionResult:
    """Result of Claude extraction for a single item."""

    url: str
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0


class ClaudeProcessor:
    """
    Uses Claude to extract structured data from scraped HTML.

    Handles both single-item pages (detail pages) and multi-item pages
    (listing pages) automatically. Claude detects the page type and returns
    either a single object or an array of objects.
    """

    SYSTEM_PROMPT = (
        "You are a precise data extraction assistant.\n"
        "Extract structured data from HTML/text exactly as specified.\n"
        "Return ONLY valid JSON matching the requested schema.\n"
        "If a field cannot be found, use null.\n"
        "Never invent or hallucinate values.\n"
        "For numeric fields, return numbers only (no currency symbols, no commas).\n"
        "For date fields, use YYYY-MM-DD format.\n"
        "IMPORTANT: If the page contains MULTIPLE items (like a product listing,\n"
        "search results, or a directory), return a JSON ARRAY of objects.\n"
        "If the page contains a SINGLE item (like a product detail page),\n"
        "return a single JSON object."
    )

    def __init__(self, config: ScraperConfig) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Copy .env.example to .env and add your key."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self.config = config
        self._cache: dict[str, list[ExtractionResult]] = {}
        self._total_tokens: int = 0

    def extract(self, page: ScrapedPage, schema: ExtractionSchema) -> list[ExtractionResult]:
        """
        Extract structured fields from a scraped page.

        Returns a list of ExtractionResult — one per item found on the page.
        A listing page yields multiple results; a detail page yields one.
        """
        if page.error:
            return [ExtractionResult(url=page.url, error=f"Skipped: {page.error}")]

        cache_key = self._cache_key(page.url, schema)
        if cache_key in self._cache:
            logger.debug(f"Cache hit: {page.url}")
            return self._cache[cache_key]

        prompt = self._build_extraction_prompt(page, schema)

        try:
            message = self._client.messages.create(
                model=self.config.claude_model,
                max_tokens=schema.max_tokens,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
            tokens = message.usage.input_tokens + message.usage.output_tokens
            self._total_tokens += tokens

            items = self._parse_response(raw, schema)

            results = []
            for item_data in items:
                item_data["_source_url"] = page.url
                results.append(
                    ExtractionResult(
                        url=page.url,
                        data=item_data,
                        raw_response=raw,
                        tokens_used=tokens // max(len(items), 1),
                    )
                )

            if not results:
                results = [
                    ExtractionResult(
                        url=page.url,
                        data={k: None for k in schema.fields} | {"_source_url": page.url},
                        raw_response=raw,
                        tokens_used=tokens,
                    )
                ]

        except anthropic.RateLimitError:
            logger.warning("Rate limited by Claude API. Waiting...")
            import time

            time.sleep(10)
            return self.extract(page, schema)

        except Exception as exc:
            logger.error(f"Claude extraction failed for {page.url}: {exc}")
            results = [ExtractionResult(url=page.url, error=str(exc))]

        self._cache[cache_key] = results
        return results

    def extract_batch(
        self,
        pages: list[ScrapedPage],
        schema: ExtractionSchema,
    ) -> list[ExtractionResult]:
        """Extract data from multiple pages with progress display. Flattens multi-item results."""
        all_results: list[ExtractionResult] = []
        valid_pages = [p for p in pages if not p.error]
        error_pages = [p for p in pages if p.error]

        for p in error_pages:
            all_results.append(ExtractionResult(url=p.url, error=f"Skipped: {p.error}"))

        if not valid_pages:
            return all_results

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("{task.completed}/{task.total} pages"),
            console=console,
        ) as progress:
            task = progress.add_task("Extracting with Claude...", total=len(valid_pages))

            for page in valid_pages:
                page_results = self.extract(page, schema)
                all_results.extend(page_results)
                progress.advance(task)

        successful = sum(1 for r in all_results if not r.error)
        console.print(
            f"  Extraction complete: [green]{successful}[/] records from "
            f"[cyan]{len(valid_pages)}[/] pages, "
            f"[dim]{self._total_tokens:,}[/] tokens used"
        )
        return all_results

    def clean_and_categorize(
        self,
        results: list[ExtractionResult],
        categories: list[str],
    ) -> list[ExtractionResult]:
        """Second-pass: categorize extracted items. Adds _category field."""
        valid = [r for r in results if not r.error and r.data]
        if not valid:
            return results

        items_json = json.dumps(
            [
                {"idx": i, "data": {k: v for k, v in r.data.items() if not k.startswith("_")}}
                for i, r in enumerate(valid)
            ],
            ensure_ascii=False,
            indent=2,
        )

        prompt = (
            f"Categorize each item below into exactly one of: {', '.join(categories)}.\n\n"
            f"Return a JSON array where each element has 'idx' (integer) and 'category' keys.\n\n"
            f"Items:\n{items_json}"
        )

        try:
            message = self._client.messages.create(
                model=self.config.claude_model,
                max_tokens=2048,
                system="You are a categorization assistant. Return only valid JSON array.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
            parsed = self._extract_json_array(raw)
            category_map = {item["idx"]: item.get("category", "Other") for item in parsed}

            for i, r in enumerate(valid):
                r.data["_category"] = category_map.get(i, "Other")

        except Exception as exc:
            logger.error(f"Batch categorization failed: {exc}")
            for r in valid:
                r.data["_category"] = "Uncategorized"

        return results

    # --- Private helpers ---

    def _build_extraction_prompt(self, page: ScrapedPage, schema: ExtractionSchema) -> str:
        """Build the extraction prompt from page content and schema fields."""
        fields_desc = "\n".join(f"- {name}: {desc}" for name, desc in schema.fields.items())

        # Use text content (much smaller, no HTML noise) as primary source
        # Fall back to truncated HTML if text is too short
        content = page.text or ""
        if len(content) < 100 and page.html:
            content = truncate_html(page.html, max_chars=12000)
            content_label = "HTML"
        else:
            content = truncate_html(content, max_chars=12000)
            content_label = "Text content"

        return (
            f"Extract the following fields from this webpage:\n\n"
            f"{fields_desc}\n\n"
            f"URL: {page.url}\n"
            f"Title: {page.title or 'N/A'}\n\n"
            f"{content_label}:\n{content}\n\n"
            f"INSTRUCTIONS:\n"
            f"- If this page lists MULTIPLE items (products, listings, entries), "
            f"return a JSON ARRAY of objects, one per item.\n"
            f"- If this page shows a SINGLE item, return a single JSON object.\n"
            f"- Use the exact field names listed above.\n"
            f"- Use null for any field you cannot find for an item."
        )

    def _parse_response(self, raw: str, schema: ExtractionSchema) -> list[dict[str, Any]]:
        """Parse Claude's response into a list of item dicts."""
        text = self._strip_markdown_fences(raw)

        # Try direct parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass

        # Fallback: find JSON array in text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Fallback: find JSON object in text
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return [parsed]
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON from Claude response: {text[:200]}")
        return [{k: None for k in schema.fields}]

    def _strip_markdown_fences(self, text: str) -> str:
        """Strip ```json ... ``` markdown fences from Claude's response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[start:end]).strip()
        return text

    def _extract_json_array(self, raw: str) -> list[dict]:
        """Extract JSON array from Claude's response."""
        text = self._strip_markdown_fences(raw)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return []

    def _cache_key(self, url: str, schema: ExtractionSchema) -> str:
        """Generate cache key from URL + schema fields."""
        combined = url + json.dumps(schema.fields, sort_keys=True)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens
