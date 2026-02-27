"""Utility helpers: user-agent rotation, rate limiting, HTTP headers."""

from __future__ import annotations

import random
import time

# Hardcoded fallback pool — real browser UAs as of 2025
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class UserAgentRotator:
    """Rotates user-agent strings using fake-useragent with hardcoded fallback."""

    def __init__(self) -> None:
        self._pool: list[str] = self._load_pool()

    def _load_pool(self) -> list[str]:
        try:
            from fake_useragent import UserAgent

            ua = UserAgent()
            return [ua.random for _ in range(20)]
        except Exception:
            return list(FALLBACK_USER_AGENTS)

    def get(self) -> str:
        """Return a random user-agent string."""
        return random.choice(self._pool)


class RateLimiter:
    """Delay-based rate limiter using monotonic clock."""

    def __init__(self, delay_sec: float = 1.0) -> None:
        self.delay_sec = delay_sec
        self._last_request: float = 0.0

    def wait(self) -> None:
        """Block until enough time has passed since last request."""
        elapsed = time.monotonic() - self._last_request
        remaining = self.delay_sec - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()


def build_headers(user_agent: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build realistic HTTP headers for a request."""
    # Note: Do NOT set Accept-Encoding manually — httpx handles content
    # encoding negotiation and decompression automatically. Setting it
    # manually causes raw compressed bytes in response.text.
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    if extra:
        headers.update(extra)
    return headers


def normalize_url(url: str) -> str:
    """Strip fragment and trailing slash for dedup comparison."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    # Remove fragment, normalize trailing slash
    clean = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.params, parsed.query, "")
    )
    return clean
