"""Data validation and cleaning utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """Check if URL has a valid HTTP(S) scheme and netloc."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def clean_text(s: str | None) -> str | None:
    """Normalize whitespace, strip control chars. Returns None for empty strings."""
    if s is None:
        return None
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s or None


def truncate_html(html: str, max_chars: int = 8000) -> str:
    """Trim HTML before sending to Claude to stay within token limits."""
    if len(html) <= max_chars:
        return html
    return html[:max_chars] + "\n... [truncated]"


def extract_domain(url: str) -> str | None:
    """Extract domain from URL for filtering."""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return None


def is_scrapeable_url(url: str) -> bool:
    """Filter out non-HTML resources (images, PDFs, etc.)."""
    skip_extensions = {
        ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
        ".zip", ".gz", ".tar", ".mp4", ".mp3", ".avi", ".mov",
        ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".ico",
    }
    try:
        path = urlparse(url).path.lower()
        return not any(path.endswith(ext) for ext in skip_extensions)
    except Exception:
        return False


@dataclass
class ValidationResult:
    """Result of validating extracted data."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    cleaned: dict[str, Any] = field(default_factory=dict)


def validate_extraction(data: dict[str, Any], schema_fields: dict[str, str]) -> ValidationResult:
    """Validate extracted data against expected schema fields."""
    errors: list[str] = []
    cleaned: dict[str, Any] = {}

    for field_name in schema_fields:
        value = data.get(field_name)
        if value is None:
            errors.append(f"Missing field: {field_name}")
            cleaned[field_name] = None
        elif isinstance(value, str):
            cleaned[field_name] = clean_text(value)
        else:
            cleaned[field_name] = value

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        cleaned=cleaned,
    )
