"""
Tests for app/services/browser.py and app/services/frontier.py.

Covers:
  browser:
    - render_mode=never  → always returns raw bytes, no Playwright
    - render_mode=always → always calls Playwright
    - render_mode=auto, non-SPA → httpx bytes returned, no Playwright
    - render_mode=auto, <noscript> → triggers Playwright re-render
    - render_mode=auto, empty <div id="root"></div> → triggers Playwright
    - render_mode=auto, populated root div → no re-render

  frontier:
    - _url_allowed: domain filtering
    - _url_allowed: exclude_patterns block
    - _url_allowed: include_patterns gate
    - depth enforcement (> max_depth skipped)
    - max_pages hard cap via Redis INCR
    - duplicate URL not re-enqueued (visited set)
    - sitemap fixture parsing (valid sitemap.xml)
    - sitemap_index fixture (nested sitemaps)
    - link extraction via lxml
    - PDF leaf enqueue when follow_pdfs=True
    - PDF NOT walked further (no child extraction)
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# BROWSER TESTS
# ===========================================================================


class TestLooksLikeSPA:
    def test_noscript_detected(self):
        from app.services.browser import _looks_like_spa
        assert _looks_like_spa(b"<html><noscript>enable JS</noscript></html>") is True

    def test_empty_root_div_detected(self):
        from app.services.browser import _looks_like_spa
        assert _looks_like_spa(b'<div id="root"></div>') is True

    def test_populated_root_div_not_spa(self):
        from app.services.browser import _looks_like_spa
        assert _looks_like_spa(b'<div id="root"><p>content</p></div>') is False

    def test_plain_html_not_spa(self):
        from app.services.browser import _looks_like_spa
        assert _looks_like_spa("<html><body><p>Hello Timișoara</p></body></html>".encode("utf-8")) is False

    def test_noscript_uppercase(self):
        from app.services.browser import _looks_like_spa
        assert _looks_like_spa(b"<NOSCRIPT>enable JS</NOSCRIPT>") is True


class TestRenderPage:
    """render_page() applies render_javascript policy correctly."""

    def _mock_pool(self, html: bytes = b"<html>rendered</html>", url: str = "https://x.ro/") -> MagicMock:
        pool = MagicMock()
        from app.services.browser import RenderResult
        pool.render = AsyncMock(return_value=RenderResult(html=html, url=url))
        return pool

    def test_never_returns_raw_no_playwright(self):
        from app.services.browser import render_page
        pool = self._mock_pool()
        result_html, final_url, used_pw = _run(
            render_page(
                "https://x.ro/",
                raw_html_bytes=b"<html>raw</html>",
                render_mode="never",
                pool=pool,
            )
        )
        assert used_pw is False
        assert result_html == b"<html>raw</html>"
        pool.render.assert_not_called()

    def test_always_calls_playwright(self):
        from app.services.browser import render_page
        rendered = b"<html>js-rendered</html>"
        pool = self._mock_pool(html=rendered)
        result_html, _url, used_pw = _run(
            render_page("https://x.ro/", render_mode="always", pool=pool)
        )
        assert used_pw is True
        assert result_html == rendered
        pool.render.assert_called_once()

    def test_auto_non_spa_no_playwright(self):
        from app.services.browser import render_page
        raw = b"<html><body><p>content</p></body></html>"
        pool = self._mock_pool()
        _html, _url, used_pw = _run(
            render_page(
                "https://x.ro/",
                raw_html_bytes=raw,
                render_mode="auto",
                pool=pool,
            )
        )
        assert used_pw is False
        pool.render.assert_not_called()

    def test_auto_noscript_triggers_playwright(self):
        from app.services.browser import render_page
        raw = b"<html><noscript>enable JS</noscript></html>"
        rendered = b"<html><body>actual content</body></html>"
        pool = self._mock_pool(html=rendered)
        result_html, _url, used_pw = _run(
            render_page(
                "https://x.ro/",
                raw_html_bytes=raw,
                render_mode="auto",
                pool=pool,
            )
        )
        assert used_pw is True
        assert result_html == rendered

    def test_auto_empty_root_div_triggers_playwright(self):
        from app.services.browser import render_page
        raw = b'<html><body><div id="root"></div></body></html>'
        pool = self._mock_pool()
        _html, _url, used_pw = _run(
            render_page(
                "https://x.ro/",
                raw_html_bytes=raw,
                render_mode="auto",
                pool=pool,
            )
        )
        assert used_pw is True

    def test_auto_no_raw_bytes_triggers_playwright(self):
        """No raw_html_bytes provided in auto mode → go straight to Playwright."""
        from app.services.browser import render_page
        pool = self._mock_pool()
        _html, _url, used_pw = _run(
            render_page("https://x.ro/", render_mode="auto", pool=pool)
        )
        assert used_pw is True


class TestCrawlRunnerFetchAdapter:
    def test_fetch_adapter_forwards_frontier_config(self):
        from app.crawl_runner import _fetch_for_frontier
        from app.services.frontier import FrontierConfig

        cfg = FrontierConfig(
            job_id="cj_test",
            tenant_id="ph-test",
            allowed_domains=["example.com"],
            user_agent="UnitTestBot/1.0",
            max_requests_per_second=2.5,
            respect_robots_txt=False,
            max_pdf_size_mb=12,
            timeout_ms=4567,
        )

        with patch("app.crawl_runner.fetch", new=AsyncMock(return_value=MagicMock())) as mocked_fetch:
            _run(_fetch_for_frontier("https://example.com/page", cfg))

        mocked_fetch.assert_awaited_once_with(
            "https://example.com/page",
            user_agent="UnitTestBot/1.0",
            follow_redirects=True,
            timeout_ms=4567,
            max_pdf_size_mb=12,
            respect_robots_txt=False,
            max_requests_per_second=2.5,
            redis=None,
        )

    def test_fetch_adapter_forwards_redis_client(self):
        from app.crawl_runner import _fetch_for_frontier
        from app.services.frontier import FrontierConfig

        cfg = FrontierConfig(
            job_id="cj_test",
            tenant_id="ph-test",
            allowed_domains=["example.com"],
            max_requests_per_second=3.0,
        )
        fake_redis = object()

        with patch("app.crawl_runner.fetch", new=AsyncMock(return_value=MagicMock())) as mocked_fetch:
            _run(
                _fetch_for_frontier(
                    "https://example.com/page",
                    cfg,
                    redis_client=fake_redis,
                )
            )

        mocked_fetch.assert_awaited_once_with(
            "https://example.com/page",
            user_agent="LexAdvisor-Bot/1.0 (+https://lex-advisor.citydock.ro/bot)",
            follow_redirects=True,
            timeout_ms=30_000,
            max_pdf_size_mb=50,
            respect_robots_txt=True,
            max_requests_per_second=3.0,
            redis=fake_redis,
        )


# ===========================================================================
# FRONTIER TESTS
# ===========================================================================


def _make_cfg(**kwargs):
    from app.services.frontier import FrontierConfig
    defaults = dict(
        job_id="cj_test123",
        tenant_id="ph-test",
        allowed_domains=["primaria-exemplu.ro"],
        max_depth=3,
        max_pages=100,
    )
    defaults.update(kwargs)
    return FrontierConfig(**defaults)


class TestUrlAllowed:
    """Domain + include/exclude pattern filtering."""

    def test_matching_domain_allowed(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(allowed_domains=["primaria-exemplu.ro"])
        assert _url_allowed("https://primaria-exemplu.ro/hcl/", cfg) is True

    def test_wrong_domain_blocked(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(allowed_domains=["primaria-exemplu.ro"])
        assert _url_allowed("https://evil.com/hcl/", cfg) is False

    def test_exclude_pattern_blocks(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(exclude_patterns=[r"/galerie-foto/"])
        assert _url_allowed("https://primaria-exemplu.ro/galerie-foto/img1", cfg) is False

    def test_exclude_pattern_image_ext(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(exclude_patterns=[r"\.(jpg|png|gif|mp4)$"])
        assert _url_allowed("https://primaria-exemplu.ro/foto/img.jpg", cfg) is False

    def test_non_excluded_url_allowed(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(exclude_patterns=[r"/galerie-foto/"])
        assert _url_allowed("https://primaria-exemplu.ro/hcl/doc.pdf", cfg) is True

    def test_include_patterns_gate_pass(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(include_patterns=[r"/hcl/", r"/dispozitii/"])
        assert _url_allowed("https://primaria-exemplu.ro/hcl/125", cfg) is True

    def test_include_patterns_gate_fail(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(include_patterns=[r"/hcl/", r"/dispozitii/"])
        assert _url_allowed("https://primaria-exemplu.ro/stiri/", cfg) is False

    def test_empty_include_patterns_allows_all_in_domain(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(include_patterns=[])
        assert _url_allowed("https://primaria-exemplu.ro/anything", cfg) is True

    def test_subdomain_of_allowed_domain_accepted(self):
        from app.services.frontier import _url_allowed
        cfg = _make_cfg(allowed_domains=["primaria-exemplu.ro"])
        # www.primaria-exemplu.ro is subdomain → allowed
        assert _url_allowed("https://www.primaria-exemplu.ro/hcl/", cfg) is True


class TestLinkExtraction:
    def test_extracts_absolute_links(self):
        from app.services.frontier import extract_links
        html = b'<html><body><a href="/hcl/125">HCL</a><a href="https://other.ro/">ext</a></body></html>'
        links = extract_links(html, "https://primaria-exemplu.ro/")
        assert any("hcl/125" in l for l in links)
        assert any("other.ro" in l for l in links)

    def test_relative_links_resolved(self):
        from app.services.frontier import extract_links
        html = b'<html><body><a href="doc.pdf">PDF</a></body></html>'
        links = extract_links(html, "https://primaria-exemplu.ro/hcl/")
        assert any("doc.pdf" in l for l in links)

    def test_no_links_returns_empty(self):
        from app.services.frontier import extract_links
        links = extract_links(b"<html><body><p>no links</p></body></html>", "https://x.ro/")
        assert links == []

    def test_javascript_links_excluded(self):
        from app.services.frontier import extract_links
        html = b'<html><body><a href="javascript:void(0)">click</a></body></html>'
        links = extract_links(html, "https://x.ro/")
        assert all("javascript:" not in l for l in links)


class TestSitemapParsing:
    def test_urlset_parsed(self):
        from app.services.frontier import _parse_sitemap
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://primaria-exemplu.ro/hcl/125</loc></url>
  <url><loc>https://primaria-exemplu.ro/hcl/126</loc></url>
</urlset>"""
        locs = _parse_sitemap(xml)
        assert len(locs) == 2
        assert "https://primaria-exemplu.ro/hcl/125" in locs

    def test_sitemap_index_returns_child_sitemaps(self):
        from app.services.frontier import _parse_sitemap
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://primaria-exemplu.ro/sitemap-hcl.xml</loc></sitemap>
  <sitemap><loc>https://primaria-exemplu.ro/sitemap-news.xml</loc></sitemap>
</sitemapindex>"""
        locs = _parse_sitemap(xml)
        assert len(locs) == 2
        assert all("sitemap" in l for l in locs)

    def test_empty_xml_returns_empty(self):
        from app.services.frontier import _parse_sitemap
        locs = _parse_sitemap(b"<urlset></urlset>")
        assert locs == []

    def test_invalid_xml_returns_empty(self):
        from app.services.frontier import _parse_sitemap
        locs = _parse_sitemap(b"not xml at all")
        assert locs == []


class TestNormaliseUrl:
    def test_strips_fragment(self):
        from app.services.frontier import _normalise_url
        assert "#section" not in _normalise_url("https://x.ro/hcl#section")

    def test_lowercase_scheme_host(self):
        from app.services.frontier import _normalise_url
        n = _normalise_url("HTTPS://Primaria-Exemplu.Ro/HCL/")
        assert n.startswith("https://primaria-exemplu.ro")

    def test_trailing_slash_stripped(self):
        from app.services.frontier import _normalise_url
        a = _normalise_url("https://x.ro/hcl/")
        b = _normalise_url("https://x.ro/hcl")
        assert a == b


class TestFrontierDepthAndCaps:
    """Depth enforcement + max_pages cap via mocked Redis."""

    def _make_redis(self, incr_value: int = 1, sadd_new: bool = True) -> MagicMock:
        redis = MagicMock()
        redis.incr = AsyncMock(return_value=incr_value)
        redis.sadd = AsyncMock(return_value=1 if sadd_new else 0)
        redis.hincrby = AsyncMock(return_value=1)
        redis.hgetall = AsyncMock(return_value={})
        return redis

    def _make_exchange(self):
        exc = MagicMock()
        exc.publish = AsyncMock()
        return exc

    def test_depth_over_max_not_enqueued(self):
        from app.services.frontier import Frontier
        cfg = _make_cfg(max_depth=2)
        redis = self._make_redis()
        frontier = Frontier(cfg, redis=redis, rmq_connection=MagicMock())
        frontier._exchange = self._make_exchange()
        frontier._channel = MagicMock()
        result = _run(frontier.enqueue("https://primaria-exemplu.ro/a", depth=3))
        assert result is False
        frontier._exchange.publish.assert_not_called()

    def test_depth_at_max_allowed(self):
        from app.services.frontier import Frontier
        cfg = _make_cfg(max_depth=2)
        redis = self._make_redis(incr_value=1)
        frontier = Frontier(cfg, redis=redis, rmq_connection=MagicMock())
        frontier._exchange = self._make_exchange()
        frontier._channel = MagicMock()
        result = _run(frontier.enqueue("https://primaria-exemplu.ro/a", depth=2))
        assert result is True

    def test_max_pages_cap_blocks_enqueue(self):
        from app.services.frontier import Frontier
        cfg = _make_cfg(max_pages=5)
        # INCR returns 6 → over cap
        redis = self._make_redis(incr_value=6)
        frontier = Frontier(cfg, redis=redis, rmq_connection=MagicMock())
        frontier._exchange = self._make_exchange()
        frontier._channel = MagicMock()
        result = _run(frontier.enqueue("https://primaria-exemplu.ro/a", depth=0))
        assert result is False

    def test_duplicate_url_not_enqueued(self):
        from app.services.frontier import Frontier
        cfg = _make_cfg()
        # sadd returns 0 → already visited
        redis = self._make_redis(sadd_new=False)
        frontier = Frontier(cfg, redis=redis, rmq_connection=MagicMock())
        frontier._exchange = self._make_exchange()
        frontier._channel = MagicMock()
        result = _run(frontier.enqueue("https://primaria-exemplu.ro/hcl/", depth=0))
        assert result is False
        frontier._exchange.publish.assert_not_called()

    def test_domain_filtered_url_not_enqueued(self):
        from app.services.frontier import Frontier
        cfg = _make_cfg(allowed_domains=["primaria-exemplu.ro"])
        redis = self._make_redis()
        frontier = Frontier(cfg, redis=redis, rmq_connection=MagicMock())
        frontier._exchange = self._make_exchange()
        frontier._channel = MagicMock()
        result = _run(frontier.enqueue("https://evil.com/hcl/", depth=0))
        assert result is False

    def test_pdf_enqueued_as_leaf_at_max_depth(self):
        """follow_pdfs=True → PDF enqueued at max_depth (no further walking)."""
        from app.services.frontier import Frontier
        cfg = _make_cfg(max_depth=3, follow_pdfs=True)
        redis = self._make_redis(incr_value=1)
        frontier = Frontier(cfg, redis=redis, rmq_connection=MagicMock())
        exchange = self._make_exchange()
        frontier._exchange = exchange
        frontier._channel = MagicMock()
        result = _run(
            frontier.enqueue("https://primaria-exemplu.ro/hcl/doc.pdf", depth=3)
        )
        assert result is True
        # message published
        exchange.publish.assert_called_once()
        # depth in published message == max_depth
        published_body = exchange.publish.call_args[0][0].body
        msg = json.loads(published_body)
        assert msg["depth"] == 3
