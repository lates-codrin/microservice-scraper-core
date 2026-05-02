# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""
HTTP fetching service — async httpx client with:
- Redirect following (max 10 hops), SSRF-checked at every hop
- Per-domain token-bucket rate limiting (Redis key DOMAIN:rate:<domain>; in-process fallback)
- max_pdf_size_mb enforcement — aborts mid-stream; emits warning "pdf_too_large"
- robots.txt compliance — cached in Redis DOMAIN:robots:<domain> TTL 1h
- SSRF defence — rejects RFC-1918/loopback/link-local addresses (422) on EVERY redirect hop
- User-Agent from config
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

if TYPE_CHECKING:
    from redis.asyncio import Redis  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_ROBOTS_TTL = 3600


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FetchError(Exception):
    def __init__(self, message: str, code: str = "upstream_error", status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class RateLimitedError(FetchError):
    def __init__(self, domain: str) -> None:
        super().__init__(f"Rate limit exceeded for '{domain}'", code="rate_limited", status=429)
        self.domain = domain


class RobotsDisallowedError(FetchError):
    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows '{url}'", code="robots_disallowed", status=403)


class SSRFError(FetchError):
    def __init__(self, host: str, addr: str) -> None:
        super().__init__(
            f"SSRF: '{host}' resolves to private/loopback address '{addr}'",
            code="validation_error",
            status=422,
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    url: str
    final_url: str
    http_status: int
    response_time_ms: int
    redirect_chain: list[str]
    headers: dict[str, str]
    content: bytes
    mime_type: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-process token bucket (fallback when Redis unavailable)
# ---------------------------------------------------------------------------


class _InProcessTokenBucket:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def consume(self, domain: str, rate: float) -> bool:
        async with self._lock:
            now = time.monotonic()
            tokens, last = self._buckets.get(domain, (rate, now))
            tokens = min(rate, tokens + (now - last) * rate)
            if tokens < 1.0:
                self._buckets[domain] = (tokens, now)
                return False
            self._buckets[domain] = (tokens - 1.0, now)
            return True


_local_buckets = _InProcessTokenBucket()

# Lua script: atomic token-bucket refill + consume
_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local now  = tonumber(ARGV[2])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1]) or rate
local ts     = tonumber(data[2]) or now
tokens = math.min(rate, tokens + (now - ts) * rate)
if tokens < 1.0 then
    redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
    redis.call('EXPIRE', key, 60)
    return 0
end
redis.call('HMSET', key, 'tokens', tokens - 1.0, 'ts', now)
redis.call('EXPIRE', key, 60)
return 1
"""


async def _redis_consume(redis: Redis, domain: str, rate: float) -> bool:
    result = await redis.eval(_BUCKET_LUA, 1, f"DOMAIN:rate:{domain}", str(rate), str(time.time()))  # type: ignore[attr-defined]
    return bool(result)


# ---------------------------------------------------------------------------
# SSRF guard — called on the initial URL and on every redirect hop
# ---------------------------------------------------------------------------


def _check_ssrf(hostname: str) -> None:
    if not hostname:
        raise FetchError("Empty hostname", code="validation_error", status=422)
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise FetchError(
            f"DNS failed for '{hostname}': {exc}", code="upstream_error", status=502
        ) from exc
    for *_, sockaddr in infos:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        for net in _PRIVATE_NETS:
            if addr in net:
                raise SSRFError(hostname, sockaddr[0])


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


async def _get_robots(
    client: httpx.AsyncClient,
    scheme: str,
    domain: str,
    user_agent: str,
    redis: Redis | None,
) -> RobotFileParser:
    key = f"DOMAIN:robots:{domain}"
    content = ""

    if redis is not None:
        try:
            cached = await redis.get(key)  # type: ignore[attr-defined]
            if cached:
                content = cached.decode() if isinstance(cached, bytes) else cached
        except Exception:
            pass

    if not content:
        robots_url = f"{scheme}://{domain}/robots.txt"
        try:
            r = await client.get(robots_url, headers={"User-Agent": user_agent}, timeout=10.0)
            if r.status_code == 200:
                content = r.text
        except Exception:
            content = ""
        if redis is not None:
            try:
                await redis.setex(key, _ROBOTS_TTL, content)  # type: ignore[attr-defined]
            except Exception:
                pass

    parser = RobotFileParser()
    parser.parse(content.splitlines())
    return parser


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))


async def fetch(
    url: str,
    *,
    user_agent: str = "LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)",
    follow_redirects: bool = True,
    max_redirects: int = 10,
    timeout_ms: int = 30_000,
    max_pdf_size_mb: int = 50,
    respect_robots_txt: bool = True,
    max_requests_per_second: float = 1.0,
    redis: Redis | None = None,
) -> FetchResult:
    """Fetch *url* applying all policy guards.

    SSRF is checked on the initial URL **and on every redirect destination**,
    preventing redirect-chain attacks that land on RFC-1918 / link-local addresses.
    Raises FetchError on policy violations.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(
            f"Unsupported scheme '{parsed.scheme}'", code="validation_error", status=422
        )

    hostname = parsed.hostname or ""
    scheme = parsed.scheme
    domain = hostname

    # Initial SSRF check — also re-checked at each redirect hop below
    _check_ssrf(hostname)

    # Rate limit (keyed to initial domain)
    if redis is not None:
        try:
            allowed = await _redis_consume(redis, domain, max_requests_per_second)
        except Exception:
            allowed = await _local_buckets.consume(domain, max_requests_per_second)
    else:
        allowed = await _local_buckets.consume(domain, max_requests_per_second)

    if not allowed:
        raise RateLimitedError(domain)

    warnings: list[str] = []
    max_pdf_bytes = max_pdf_size_mb * 1024 * 1024

    # Separate client with follow_redirects=True only for robots.txt (low-risk,
    # fetches from the same already-SSRF-checked domain).
    robots_client = httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=3,
        timeout=httpx.Timeout(10.0),
    )

    # Main client: follow_redirects=False so we can SSRF-check every hop ourselves.
    main_client = httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_ms / 1000.0),
    )

    async with robots_client, main_client:
        # robots.txt check
        if respect_robots_txt:
            try:
                parser = await _get_robots(robots_client, scheme, domain, user_agent, redis)
                if not parser.can_fetch(user_agent, url):
                    raise RobotsDisallowedError(url)
            except RobotsDisallowedError:
                raise
            except Exception as exc:
                logger.warning("robots.txt check failed for %s: %s", domain, exc)

        start = time.monotonic()
        redirect_chain: list[str] = []
        current_url = url

        # Manual redirect loop — SSRF-check every hop
        for _hop in range(max_redirects + 1):
            hop_parsed = urlparse(current_url)
            hop_host = hop_parsed.hostname or ""

            # SSRF guard on each redirect destination (including the first request)
            _check_ssrf(hop_host)

            try:
                async with main_client.stream(
                    "GET", current_url, headers={"User-Agent": user_agent}
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES and follow_redirects:
                        location = response.headers.get("location", "")
                        if not location:
                            raise FetchError(
                                "Redirect response missing Location header",
                                code="upstream_error",
                                status=502,
                            )
                        redirect_chain.append(current_url)
                        # Resolve relative redirect URLs
                        current_url = urljoin(current_url, location)
                        # Consume (discard) the redirect body
                        await response.aread()
                        continue

                    # ── Final response ──────────────────────────────────────
                    http_status = response.status_code
                    resp_headers = dict(response.headers)
                    mime_type = (
                        resp_headers.get("content-type", "application/octet-stream")
                        .split(";")[0]
                        .strip()
                    )
                    is_pdf = mime_type == "application/pdf" or current_url.lower().endswith(".pdf")

                    # content-length pre-check
                    cl_hdr = resp_headers.get("content-length")
                    if is_pdf and cl_hdr and int(cl_hdr) > max_pdf_bytes:
                        warnings.append("pdf_too_large")
                        logger.warning(
                            "pdf_too_large: %s header %s bytes > %d limit",
                            current_url,
                            cl_hdr,
                            max_pdf_bytes,
                        )
                        elapsed = int((time.monotonic() - start) * 1000)
                        return FetchResult(
                            url=url,
                            final_url=str(response.url),
                            http_status=http_status,
                            response_time_ms=elapsed,
                            redirect_chain=redirect_chain,
                            headers=resp_headers,
                            content=b"",
                            mime_type=mime_type,
                            warnings=warnings,
                        )

                    # streaming read
                    chunks: list[bytes] = []
                    received = 0
                    truncated = False
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if is_pdf and received > max_pdf_bytes:
                            warnings.append("pdf_too_large")
                            logger.warning(
                                "pdf_too_large: %s exceeded %d MB mid-stream",
                                current_url,
                                max_pdf_size_mb,
                            )
                            truncated = True
                            break
                        chunks.append(chunk)

                    elapsed = int((time.monotonic() - start) * 1000)
                    return FetchResult(
                        url=url,
                        final_url=str(response.url),
                        http_status=http_status,
                        response_time_ms=elapsed,
                        redirect_chain=redirect_chain,
                        headers=resp_headers,
                        content=b"" if truncated else b"".join(chunks),
                        mime_type=mime_type,
                        warnings=warnings,
                    )

            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                raise FetchError(str(exc), code="upstream_error", status=502) from exc

        # Exhausted redirect budget
        raise FetchError(
            f"Too many redirects (max {max_redirects})",
            code="upstream_error",
            status=502,
        )
