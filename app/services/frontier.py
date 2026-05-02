# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
Crawl frontier ” async BFS via RabbitMQ + Redis.

Queue topology:
  exchange : crawl        (direct)
  queue    : urls.<job_id>

Each message JSON:
  {url, depth, job_id, tenant_id}

Redis keys:
  JOB:pages:<job_id>         INCR counter (max_pages hard cap)
  JOB:visited:<job_id>       SET of normalised URLs already enqueued
  JOB:progress:<job_id>      HASH: urls_discovered, urls_fetched,
                                   urls_pending, bytes_downloaded

Workers pull from RabbitMQ; no in-process queue.

Sitemap: if sitemap_hint_url set, parse sitemap.xml / sitemap_index.xml,
seed frontier from sitemap first, then fall back to link walking.

URL filtering rules (applied before enqueue):
  1. host in allowed_domains
  2. not matched by any exclude_pattern
  3. if include_patterns non-empty  at least one must match

PDF links: if follow_pdfs=True, enqueue .pdf URLs as leaf nodes
  (no further link extraction after fetch).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

if TYPE_CHECKING:
    from redis.asyncio import Redis  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_EXCHANGE = "crawl"
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Redis key templates
_KEY_PAGES = "JOB:pages:{job_id}"
_KEY_VISITED = "JOB:visited:{job_id}"
_KEY_PROGRESS = "JOB:progress:{job_id}"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _normalise_url(url: str) -> str:
    """Strip fragment; lowercase scheme+host; remove trailing slash from path."""
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, p.params, p.query, ""))


def _is_pdf_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


@dataclass
class FrontierConfig:
    job_id: str
    tenant_id: str
    allowed_domains: list[str]
    max_depth: int = 5
    max_pages: int = 2000
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    follow_pdfs: bool = True
    render_javascript: str = "auto"
    sitemap_hint_url: str | None = None
    user_agent: str = "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)"
    max_requests_per_second: float = 1.0
    respect_robots_txt: bool = True
    max_pdf_size_mb: int = 50
    timeout_ms: int = 30_000


def _domain_allowed(url: str, cfg: FrontierConfig) -> bool:
    """Return True if URL's host is in allowed_domains (domain check only)."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in cfg.allowed_domains)


def _url_allowed(url: str, cfg: FrontierConfig, *, skip_include_patterns: bool = False) -> bool:
    """Return True if URL passes domain + include/exclude pattern filters.

    skip_include_patterns=True used for depth-0 seeds ” they are explicit
    entrypoints, not discovered links, so include_patterns should not gate them.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]  # strip port

    # Domain check
    if not any(host == d.lower() or host.endswith("." + d.lower()) for d in cfg.allowed_domains):
        return False

    path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")

    # Exclude patterns
    for pat in cfg.exclude_patterns:
        try:
            if re.search(pat, path_and_query):
                return False
        except re.error:
            logger.warning("Invalid exclude_pattern regex: %r", pat)

    # Include patterns (any-match gate, only when non-empty)
    # Skipped for seed URLs ” they're caller-supplied entrypoints.
    if cfg.include_patterns and not skip_include_patterns:
        matched = False
        for pat in cfg.include_patterns:
            try:
                if re.search(pat, path_and_query):
                    matched = True
                    break
            except re.error:
                logger.warning("Invalid include_pattern regex: %r", pat)
        if not matched:
            return False

    return True


# ---------------------------------------------------------------------------
# Link extraction (lxml)
# ---------------------------------------------------------------------------


def extract_links(html: bytes, base_url: str) -> list[str]:
    """Extract all <a href> from HTML; normalise to absolute URLs."""
    try:
        from lxml import html as lxml_html  # type: ignore[import-untyped]

        doc = lxml_html.fromstring(html, base_url=base_url)
        doc.make_links_absolute(base_url, resolve_base_href=True)
        links: list[str] = []
        for element, _attr, href, _pos in doc.iterlinks():
            if element.tag == "a" and href:
                p = urlparse(href)
                if p.scheme in ("http", "https"):
                    links.append(href)
        return links
    except Exception as exc:
        logger.warning("link extraction failed for %s: %s", base_url, exc)
        return []


# ---------------------------------------------------------------------------
# Sitemap parsing
# ---------------------------------------------------------------------------


async def _fetch_bytes(url: str, user_agent: str, timeout_ms: int) -> bytes:
    """Simple httpx GET; used for sitemap and robots fetches."""
    import httpx

    async with httpx.AsyncClient(timeout=timeout_ms / 1000.0) as client:
        r = await client.get(url, headers={"User-Agent": user_agent})
        r.raise_for_status()
        return r.content


def _parse_sitemap(xml_bytes: bytes) -> list[str]:
    """Parse sitemap.xml or sitemap_index.xml; return list of loc URLs."""
    try:
        from lxml import etree  # type: ignore[import-untyped]

        root = etree.fromstring(xml_bytes)
        ns = {"sm": _SITEMAP_NS}
        # sitemap_index  nested sitemaps
        sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
        if sitemaps:
            return [el.text.strip() for el in sitemaps if el.text]
        # urlset  page URLs
        urls = root.findall(".//sm:url/sm:loc", ns)
        return [el.text.strip() for el in urls if el.text]
    except Exception as exc:
        logger.warning("sitemap parse error: %s", exc)
        return []


async def seed_from_sitemap(
    sitemap_url: str,
    *,
    user_agent: str,
    timeout_ms: int,
    max_pages: int,
) -> list[str]:
    """Fetch and recursively parse sitemap / sitemap_index; return up to max_pages URLs."""
    try:
        xml = await _fetch_bytes(sitemap_url, user_agent, timeout_ms)
    except Exception as exc:
        logger.warning("sitemap fetch failed %s: %s", sitemap_url, exc)
        return []

    locs = _parse_sitemap(xml)
    results: list[str] = []

    for loc in locs:
        if len(results) >= max_pages:
            break
        if loc.endswith(".xml") or "sitemap" in loc.lower():
            # Nested sitemap index  recurse one level
            try:
                sub_xml = await _fetch_bytes(loc, user_agent, timeout_ms)
                sub_locs = _parse_sitemap(sub_xml)
                results.extend(sub_locs[: max_pages - len(results)])
            except Exception as exc:
                logger.warning("nested sitemap fetch failed %s: %s", loc, exc)
        else:
            results.append(loc)

    return results[:max_pages]


# ---------------------------------------------------------------------------
# RabbitMQ helpers
# ---------------------------------------------------------------------------


async def _get_channel(connection):  # type: ignore[return]
    """Return a fresh channel from an aio-pika connection."""
    return await connection.channel()


async def _declare_queue(channel, job_id: str):  # type: ignore[return]
    """Declare exchange + queue; return queue object."""
    import aio_pika  # type: ignore[import-untyped]

    exchange = await channel.declare_exchange(_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue(f"urls.{job_id}", durable=True, auto_delete=False)
    await queue.bind(exchange, routing_key=f"urls.{job_id}")
    return exchange, queue


async def _publish(exchange, job_id: str, url: str, depth: int, tenant_id: str) -> None:
    """Publish one URL message to RabbitMQ exchange."""
    import aio_pika  # type: ignore[import-untyped]

    body = json.dumps(
        {"url": url, "depth": depth, "job_id": job_id, "tenant_id": tenant_id}
    ).encode()
    await exchange.publish(
        aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key=f"urls.{job_id}",
    )


# ---------------------------------------------------------------------------
# Redis progress helpers
# ---------------------------------------------------------------------------


async def _redis_incr_pages(redis: Redis, job_id: str) -> int:
    """Atomic INCR on page counter; return new count."""
    return int(await redis.incr(_KEY_PAGES.format(job_id=job_id)))  # type: ignore[attr-defined]


async def _redis_mark_visited(redis: Redis, job_id: str, norm_url: str) -> bool:
    """SADD; return True if newly added (not previously seen)."""
    return bool(await redis.sadd(_KEY_VISITED.format(job_id=job_id), norm_url))  # type: ignore[attr-defined]


async def _redis_update_progress(redis: Redis, job_id: str, **fields: int) -> None:
    if not fields:
        return
    await redis.hset(  # type: ignore[attr-defined]
        _KEY_PROGRESS.format(job_id=job_id),
        mapping={k: str(v) for k, v in fields.items()},
    )


async def _redis_hincrby(redis: Redis, job_id: str, field: str, amount: int = 1) -> None:
    await redis.hincrby(_KEY_PROGRESS.format(job_id=job_id), field, amount)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Frontier
# ---------------------------------------------------------------------------


class Frontier:
    """
    Orchestrate a BFS crawl for one job.

    Typical usage:
        frontier = Frontier(cfg, redis=redis, rmq_connection=conn)
        await frontier.start()          # seed queue
        # workers call frontier.process_message() in a loop
    """

    def __init__(
        self,
        cfg: FrontierConfig,
        *,
        redis: Redis,
        rmq_connection,  # aio_pika connection
    ) -> None:
        self._cfg = cfg
        self._redis = redis
        self._rmq = rmq_connection
        self._channel = None
        self._exchange = None
        self._queue = None

    async def _ensure_channel(self):
        if self._channel is None:
            self._channel = await _get_channel(self._rmq)
            self._exchange, self._queue = await _declare_queue(self._channel, self._cfg.job_id)

    async def start(self, seed_urls: list[str]) -> None:
        """
        Seed the RabbitMQ queue.
        1. If sitemap_hint_url  fetch sitemap first (filtered through url_allowed).
        2. Then enqueue seed_urls at depth=0.
        """
        await self._ensure_channel()
        cfg = self._cfg

        sitemap_urls: list[str] = []
        if cfg.sitemap_hint_url:
            sitemap_urls = await seed_from_sitemap(
                cfg.sitemap_hint_url,
                user_agent=cfg.user_agent,
                timeout_ms=cfg.timeout_ms,
                max_pages=cfg.max_pages,
            )
            logger.info("job=%s sitemap produced %d URLs", cfg.job_id, len(sitemap_urls))

        # Combine: sitemap first, then seed_urls
        all_seeds = sitemap_urls + seed_urls
        enqueued = 0
        for url in all_seeds:
            if enqueued >= cfg.max_pages:
                break
            norm = _normalise_url(url)
            # Seeds bypass include_patterns ” they are explicit entrypoints.
            # Exclude-patterns and domain checks still apply.
            if not _url_allowed(url, cfg, skip_include_patterns=True):
                logger.debug("job=%s seed filtered (domain/exclude): %s", cfg.job_id, url)
                continue
            newly_added = await _redis_mark_visited(self._redis, cfg.job_id, norm)
            if not newly_added:
                continue
            await _publish(self._exchange, cfg.job_id, url, depth=0, tenant_id=cfg.tenant_id)
            enqueued += 1
            await _redis_hincrby(self._redis, cfg.job_id, "urls_discovered")
            await _redis_hincrby(self._redis, cfg.job_id, "urls_pending")

        logger.info("job=%s seeded %d URLs into RabbitMQ", cfg.job_id, enqueued)

    async def enqueue(self, url: str, depth: int) -> bool:
        """
        Enqueue *url* if it passes all filters and caps.
        Returns True if actually enqueued.
        """
        await self._ensure_channel()
        cfg = self._cfg

        if depth > cfg.max_depth:
            return False

        if not _url_allowed(url, cfg):
            return False

        norm = _normalise_url(url)
        newly_added = await _redis_mark_visited(self._redis, cfg.job_id, norm)
        if not newly_added:
            return False  # already seen

        # Hard page cap (atomic INCR)
        count = await _redis_incr_pages(self._redis, cfg.job_id)
        if count > cfg.max_pages:
            # Over cap ” don't enqueue
            return False

        await _publish(self._exchange, cfg.job_id, url, depth=depth, tenant_id=cfg.tenant_id)
        await _redis_hincrby(self._redis, cfg.job_id, "urls_discovered")
        await _redis_hincrby(self._redis, cfg.job_id, "urls_pending")
        return True

    async def process_message(
        self,
        message_body: bytes,
        *,
        fetch_fn,  # async callable(url, cfg) -> FetchResult
        extract_fn,  # sync callable(content, mime_type) -> ExtractionResult
        browser_render_fn,  # async callable(url, raw_bytes, mode) -> (bytes, str, bool)
        include_raw_html: bool = False,
    ) -> dict:
        """
        Process one RabbitMQ message:
        1. Decode {url, depth, job_id, tenant_id}
        2. Fetch via httpx (fetch_fn)
        3. Apply render_javascript logic (browser_render_fn)
        4. Extract links  enqueue children (depth+1)
        5. Return extracted document dict
        """
        cfg = self._cfg
        msg = json.loads(message_body)
        url: str = msg["url"]
        depth: int = msg["depth"]
        is_pdf = _is_pdf_url(url)

        # --- Fetch ---
        fetch_result = await fetch_fn(url, cfg)

        # Update bytes_downloaded
        await _redis_hincrby(
            self._redis,
            cfg.job_id,
            "bytes_downloaded",
            len(fetch_result.content),
        )

        # --- Render if HTML ---
        html_bytes = fetch_result.content
        final_url = fetch_result.final_url
        used_playwright = False
        raw_html_for_doc: str | None = None

        if not is_pdf and "html" in fetch_result.mime_type:
            html_bytes, final_url, used_playwright = await browser_render_fn(
                final_url,
                raw_html_bytes=fetch_result.content,
                render_mode=cfg.render_javascript,
            )
            if include_raw_html:
                raw_html_for_doc = html_bytes.decode("utf-8", errors="replace")

        # --- Extract ---
        extraction = extract_fn(html_bytes, fetch_result.mime_type)

        # --- Link extraction + enqueue children ---
        if not is_pdf and "html" in fetch_result.mime_type and depth < cfg.max_depth:
            links = extract_links(html_bytes, final_url)
            for link in links:
                if cfg.follow_pdfs and _is_pdf_url(link):
                    # PDF leaf ” enqueue at max_depth so it's fetched but not walked
                    await self.enqueue(link, depth=cfg.max_depth)
                else:
                    await self.enqueue(link, depth=depth + 1)

        # Update progress counters
        await _redis_hincrby(self._redis, cfg.job_id, "urls_fetched")
        # urls_pending: decrement by 1 (this message consumed)
        await self._redis.hincrby(  # type: ignore[attr-defined]
            _KEY_PROGRESS.format(job_id=cfg.job_id), "urls_pending", -1
        )

        doc = {
            "source_url": url,
            "final_url": final_url,
            "depth": depth,
            "mime_type": fetch_result.mime_type,
            "http_status": fetch_result.http_status,
            "response_time_ms": fetch_result.response_time_ms,
            "redirect_chain": fetch_result.redirect_chain,
            "headers": fetch_result.headers,
            "raw_html": raw_html_for_doc,
            "extraction": extraction,
            "used_playwright": used_playwright,
            "warnings": fetch_result.warnings,
        }
        return doc

    async def get_progress(self) -> dict[str, int]:
        """Read current progress counters from Redis."""
        raw = await self._redis.hgetall(  # type: ignore[attr-defined]
            _KEY_PROGRESS.format(job_id=self._cfg.job_id)
        )
        return {k.decode(): int(v) for k, v in raw.items()}

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
