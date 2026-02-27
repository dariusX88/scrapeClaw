"""Configuration management: YAML loading → typed dataclasses."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env from project root (override=True so .env takes precedence over shell env)
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Base directories
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
SITES_DIR = CONFIG_DIR / "sites"


@dataclass
class RateLimitConfig:
    delay_sec: float = 1.5
    max_retries: int = 3
    retry_wait_min: float = 1.0
    retry_wait_max: float = 5.0


@dataclass
class ProxyConfig:
    enabled: bool = False
    urls: list[str] = field(default_factory=list)


@dataclass
class ExtractionSchema:
    """Claude extraction field definitions loaded from YAML."""

    fields: dict[str, str] = field(default_factory=dict)  # field_name → description
    output_format: str = "json"
    max_tokens: int = 2048


@dataclass
class ExcelThemeConfig:
    header_color: str = "1A3A5C"
    header_font_color: str = "FFFFFF"
    alt_row_color: str = "EBF2FA"
    accent_color: str = "2980B9"
    border_color: str = "B0C4D8"


@dataclass
class SiteConfig:
    """Per-site scraping configuration."""

    name: str = "unnamed"
    base_url: str = ""
    start_url: str = ""
    allowed_domains: list[str] = field(default_factory=list)
    max_pages: int = 50
    max_entries: int = 500
    js_required: bool = False
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    extraction: ExtractionSchema | None = None
    css_selectors: dict[str, str] = field(default_factory=dict)
    custom_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ScraperConfig:
    """Global scraper configuration."""

    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096
    output_dir: str = "./output"
    log_level: str = "INFO"
    excel_theme: ExcelThemeConfig = field(default_factory=ExcelThemeConfig)


class ConfigManager:
    """Load global config and per-site configs from YAML files."""

    def load_global(self) -> ScraperConfig:
        """Load config/config.yaml → ScraperConfig, with env var overrides."""
        raw = self._load_yaml(CONFIG_DIR / "config.yaml")
        if raw is None:
            raw = {}

        scraper = raw.get("scraper", {})
        claude = raw.get("claude", {})
        output = raw.get("output", {})
        logging_cfg = raw.get("logging", {})
        theme_raw = output.get("excel_theme", {})

        return ScraperConfig(
            rate_limit=self._build_rate_limit(scraper.get("rate_limit", {})),
            proxy=self._build_proxy(scraper.get("proxy", {})),
            claude_model=claude.get("model", "claude-sonnet-4-20250514"),
            claude_max_tokens=claude.get("max_tokens", 4096),
            output_dir=os.getenv("SCRAPECLAW_OUTPUT_DIR", output.get("dir", "./output")),
            log_level=os.getenv("SCRAPECLAW_LOG_LEVEL", logging_cfg.get("level", "INFO")),
            excel_theme=ExcelThemeConfig(
                header_color=theme_raw.get("header_color", "1A3A5C"),
                header_font_color=theme_raw.get("header_font_color", "FFFFFF"),
                alt_row_color=theme_raw.get("alt_row_color", "EBF2FA"),
                accent_color=theme_raw.get("accent_color", "2980B9"),
                border_color=theme_raw.get("border_color", "B0C4D8"),
            ),
        )

    def load_site(self, site_name: str) -> SiteConfig:
        """Load config/sites/<site_name>.yaml → SiteConfig."""
        path = SITES_DIR / f"{site_name}.yaml"
        raw = self._load_yaml(path)
        if raw is None:
            raise FileNotFoundError(
                f"Site config not found: {path}\n"
                f"Create one with: python main.py init-config {site_name} <url>"
            )

        from urllib.parse import urlparse

        base_url = raw.get("base_url", "")
        start_url = raw.get("start_url", base_url)
        domain = urlparse(base_url).netloc if base_url else ""
        allowed = raw.get("allowed_domains", [domain] if domain else [])

        extraction = None
        ext_raw = raw.get("extraction")
        if ext_raw and isinstance(ext_raw, dict):
            extraction = ExtractionSchema(
                fields=ext_raw.get("fields", {}),
                output_format=ext_raw.get("output_format", "json"),
                max_tokens=ext_raw.get("max_tokens", 2048),
            )

        return SiteConfig(
            name=raw.get("name", site_name),
            base_url=base_url,
            start_url=start_url,
            allowed_domains=allowed,
            max_pages=raw.get("max_pages", 50),
            max_entries=raw.get("max_entries", 500),
            js_required=raw.get("js_required", False),
            rate_limit=self._build_rate_limit(raw.get("rate_limit", {})),
            extraction=extraction,
            css_selectors=raw.get("css_selectors", {}),
            custom_headers=raw.get("custom_headers", {}),
        )

    def create_site_template(self, site_name: str, url: str) -> Path:
        """Generate a site config template YAML file."""
        from urllib.parse import urlparse

        domain = urlparse(url).netloc
        SITES_DIR.mkdir(parents=True, exist_ok=True)

        template = {
            "name": site_name,
            "base_url": url,
            "start_url": url,
            "allowed_domains": [domain],
            "max_pages": 30,
            "max_entries": 200,
            "js_required": False,
            "rate_limit": {
                "delay_sec": 2.0,
            },
            "css_selectors": {
                "title": "h1",
                "content": "main",
            },
            "custom_headers": {
                "Accept-Language": "en-US,en;q=0.9",
            },
            "extraction": {
                "fields": {
                    "title": "Page or listing title",
                    "description": "Brief description, max 200 chars",
                    "url": "Direct link to the item",
                    "category": "Category or type",
                },
                "output_format": "json",
                "max_tokens": 2048,
            },
        }

        path = SITES_DIR / f"{site_name}.yaml"
        with open(path, "w") as f:
            yaml.dump(template, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        return path

    def list_sites(self) -> list[str]:
        """Return list of available site config names."""
        if not SITES_DIR.exists():
            return []
        return sorted(p.stem for p in SITES_DIR.glob("*.yaml"))

    # --- Private helpers ---

    def _load_yaml(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def _build_rate_limit(self, raw: dict) -> RateLimitConfig:
        return RateLimitConfig(
            delay_sec=raw.get("delay_sec", 1.5),
            max_retries=raw.get("max_retries", 3),
            retry_wait_min=raw.get("retry_wait_min", 1.0),
            retry_wait_max=raw.get("retry_wait_max", 5.0),
        )

    def _build_proxy(self, raw: dict) -> ProxyConfig:
        return ProxyConfig(
            enabled=raw.get("enabled", False),
            urls=raw.get("urls", []),
        )
