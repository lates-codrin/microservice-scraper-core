# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
Browser rendering service â€” async Playwright Chromium pool.

Pool size: BROWSER_WORKERS env var (default 4).

render_javascript modes:
  "always"  â†’ always Playwright
  "never"   â†’ always httpx (caller must pass raw bytes via fetch())
  "auto"    â†’ httpx first; if response HTML looks like SPA shell
               (<noscript> present OR <div id="root"></div> with no children)
               re-fetch with Playwright.

include_raw_html=True â†’ attach post-render HTML to result.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_BROWSER_WORKERS: int = int(os.environ.get("BROWSER_WORKERS", "4"))

# Sentinel: detect SPA shell patterns in httpx HTML response
_SPA_MARKERS = [
    b"<noscript>",
    b"<NOSCRIPT>",
]


def _looks_like_spa(html_bytes: bytes) -> bool:
    """Return True if HTML looks like an unrendered SPA shell."""
    # Check <noscript>
    for marker in _SPA_MARKERS:
        if marker in html_bytes:
            return True
    # Check <div id="root"></div> with no children (empty root)
    import re
    pattern = rb'<div\s+id=["\']root["\'][^>]*>\s*</div>'
    if re.search(pattern, html_bytes, re.IGNORECASE):
        return True
    return False


@dataclass
class RenderResult:
    html: bytes
    url: str  # final URL after JS navigation
    warnings: list[str] = field(default_factory=list)


class BrowserPool:
    """
    Async Playwright Chromium pool.  Acquire a page via the async context manager.
    Lazy-initialised on first use so import doesn't fail without Playwright installed.
    """

    def __init__(self, size: int = _BROWSER_WORKERS) -> None:
        self._size = size
        self._playwright = None
        self._browser = None
        self._sem: asyncio.Semaphore | None = None
        self._lock = asyncio.Lock()
        self._started = False

    async def _start(self) -> None:
        async with self._lock:
            if self._started:
                return
            try:
                from playwright.async_api import async_playwright  # type: ignore[import-untyped]
            except ImportError as exc:
                raise RuntimeError(
                    "playwright not installed â€” add 'playwright' to requirements.txt"
                ) from exc
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._sem = asyncio.Semaphore(self._size)
            self._started = True
            logger.info("BrowserPool started (size=%d)", self._size)

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._started = False

    async def render(
        self,
        url: str,
        *,
        timeout_ms: int = 30_000,
        user_agent: str = "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)",
    ) -> RenderResult:
        """Render *url* with Playwright; return post-JS HTML bytes."""
        await self._start()
        assert self._sem is not None
        assert self._browser is not None
        async with self._sem:
            ctx = await self._browser.new_context(user_agent=user_agent)
            try:
                page = await ctx.new_page()
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                final_url = page.url
                html = await page.content()
                return RenderResult(html=html.encode("utf-8"), url=final_url)
            except Exception as exc:
                logger.warning("Playwright render failed for %s: %s", url, exc)
                raise
            finally:
                await ctx.close()


# Module-level singleton; replaced in tests via dependency injection.
_pool: BrowserPool | None = None


def get_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool


# ---------------------------------------------------------------------------
# High-level render function used by fetcher/frontier
# ---------------------------------------------------------------------------


async def render_page(
    url: str,
    *,
    raw_html_bytes: bytes | None = None,
    render_mode: str = "auto",
    include_raw_html: bool = False,
    timeout_ms: int = 30_000,
    user_agent: str = "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)",
    pool: BrowserPool | None = None,
) -> tuple[bytes, str, bool]:
    """
    Apply render_javascript policy.

    Returns (html_bytes, final_url, used_playwright).
      html_bytes  â€” final HTML (post-render if Playwright used)
      final_url   â€” URL after any JS-driven navigation
      used_playwright â€” True when Playwright was invoked
    """
    _pool = pool or get_pool()

    if render_mode == "never":
        # Caller already has httpx bytes; return as-is
        return (raw_html_bytes or b"", url, False)

    if render_mode == "always":
        result = await _pool.render(url, timeout_ms=timeout_ms, user_agent=user_agent)
        return (result.html, result.url, True)

    # "auto" â€” use httpx bytes if provided, else just fetch via Playwright
    if raw_html_bytes and not _looks_like_spa(raw_html_bytes):
        return (raw_html_bytes, url, False)

    # Looks like SPA (or no bytes given) â†’ Playwright
    result = await _pool.render(url, timeout_ms=timeout_ms, user_agent=user_agent)
    return (result.html, result.url, True)

