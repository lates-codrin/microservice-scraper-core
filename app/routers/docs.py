# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Interactive API documentation endpoints (Scalar + ReDoc)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.settings import settings

router = APIRouter(tags=["docs"])

_UUID_INJECTOR_JS = """
<style>
  .uuid-gen-btn {
    all: unset;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 5px;
    margin-right: 2px;
    color: #a78bfa;
    background: rgba(167,139,250,0.10);
    border: 1px solid rgba(167,139,250,0.25);
    transition: background 0.15s, color 0.15s, border-color 0.15s;
    flex-shrink: 0;
    position: relative;
    z-index: 10;
  }
  .uuid-gen-btn:hover {
    background: rgba(167,139,250,0.22);
    border-color: rgba(167,139,250,0.55);
    color: #c4b5fd;
  }
  .uuid-gen-btn:active { transform: scale(0.91); }
  .uuid-gen-btn svg {
    width: 12px;
    height: 12px;
    pointer-events: none;
  }
  /* Tooltip */
  .uuid-gen-btn::after {
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    background: #1e1e2e;
    color: #e2e8f0;
    font-size: 11px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    white-space: nowrap;
    padding: 4px 8px;
    border-radius: 5px;
    border: 1px solid rgba(255,255,255,0.12);
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.14s;
    z-index: 9999;
  }
  .uuid-gen-btn:hover::after { opacity: 1; }
  .uuid-gen-btn.flash {
    color: #34d399;
    border-color: rgba(52,211,153,0.5);
    background: rgba(52,211,153,0.12);
  }
</style>
<script>
(function () {
  // Scalar stamps the <tr id="Idempotency-Key"> etc. ” use that, never text-scan.
  const UUID_HEADERS = ['Idempotency-Key', 'X-Request-ID', 'X-Request-Id'];

  const DICE_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="3"/>
    <circle cx="8"  cy="8"  r="1.2" fill="currentColor" stroke="none"/>
    <circle cx="16" cy="8"  r="1.2" fill="currentColor" stroke="none"/>
    <circle cx="8"  cy="16" r="1.2" fill="currentColor" stroke="none"/>
    <circle cx="16" cy="16" r="1.2" fill="currentColor" stroke="none"/>
    <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>
  </svg>`;

  function uuidv4() {
    return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
      (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    );
  }

  /**
   * Scalar uses CodeMirror 6 ” the value field is a contenteditable div,
   * NOT an <input>. The only reliable way to update it (so CM6 sees the
   * change and persists it) is to focus  select-all  execCommand insertText.
   */
  function fillCM6(valueCell, uuid) {
    const cm = valueCell.querySelector('.cm-content[contenteditable="true"]');
    if (!cm) return;
    cm.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, uuid);
  }

  function inject() {
    for (const name of UUID_HEADERS) {
      // Scalar sets the header name as the <tr> id ” one exact match, no duplicates.
      const row = document.querySelector(`tr[id="${name}"]`);
      if (!row || row.dataset.uuidDone) continue;

      // Row layout: td[checkbox] | td[key-label] | td[value]
      // row.children works fine even though tr has display:contents in CSS.
      const tds = [...row.children].filter(n => n.tagName === 'TD');
      if (tds.length < 3) continue;
      const valueCell = tds[tds.length - 1];

      // Scalar already has an action-button strip (absolute right-0) in the
      // value cell (holds the â„¹ï¸Ž button). Inject our button there.
      const actionsStrip = valueCell.querySelector('.centered-y.absolute');
      if (!actionsStrip) continue;

      // Mark before anything else so the observer never double-injects
      row.dataset.uuidDone = '1';

      const btn = document.createElement('button');
      btn.className   = 'uuid-gen-btn';
      btn.type        = 'button';
      btn.setAttribute('data-tip', `Generate UUID  ${name}`);
      btn.innerHTML   = DICE_SVG;

      btn.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        fillCM6(valueCell, uuidv4());
        btn.classList.add('flash');
        setTimeout(() => btn.classList.remove('flash'), 650);
      });

      // Prepend so it sits left of the â„¹ï¸Ž button
      actionsStrip.prepend(btn);
    }
  }

  // Scalar is a Vue SPA ” the request panel is torn down and rebuilt on every
  // route change, so we need the observer to re-inject on each render.
  const observer = new MutationObserver(() => {
    clearTimeout(observer._tid);
    observer._tid = setTimeout(inject, 160);
  });

  function start() {
    inject();
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    setTimeout(start, 0);
  }
})();
</script>
"""


def _get_scalar_html(spec_url: str) -> str:
    """Generate HTML for Scalar interactive API documentation."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lex-Advisor Scraper API - Scalar</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
            * {{ margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                             "Helvetica Neue", Arial, sans-serif;
                background: #0f1419;
                color: #fff;
            }}
        </style>
    </head>
    <body>
        <script
            id="api-reference"
            data-url="{spec_url}"
            data-configuration='{{"theme":"purple","hideDownloadButton":false}}'
            src="https://cdn.jsdelivr.net/npm/@scalar/api-reference">
        </script>
        {_UUID_INJECTOR_JS}
    </body>
    </html>
    """


def _get_redoc_html(spec_url: str) -> str:
    """Generate HTML for ReDoc read-only API documentation."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lex-Advisor Scraper API - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700"
              rel="stylesheet">
        <style>
            body {{ margin: 0; padding: 0; background: #fafafa; }}
        </style>
    </head>
    <body>
        <redoc spec-url='{spec_url}'></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """


@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def get_scalar_docs() -> str:
    """Serve interactive Scalar API documentation."""
    if not settings.docs_enabled:
        raise HTTPException(status_code=404, detail="Documentation disabled")
    return _get_scalar_html("/v1/openapi.json")


@router.get("/v1/docs", response_class=HTMLResponse, include_in_schema=False)
async def get_scalar_docs_v1() -> str:
    return await get_scalar_docs()


@router.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def get_redoc_docs() -> str:
    """Serve read-only ReDoc API documentation."""
    if not settings.docs_enabled:
        raise HTTPException(status_code=404, detail="Documentation disabled")
    return _get_redoc_html("/v1/openapi.json")


@router.get("/v1/redoc", response_class=HTMLResponse, include_in_schema=False)
async def get_redoc_docs_v1() -> str:
    return await get_redoc_docs()


@router.get("/docs/health", status_code=status.HTTP_200_OK, include_in_schema=False)
async def docs_health_badge() -> JSONResponse:
    """Health check endpoint for Scalar sidebar status badge."""
    if not settings.docs_enabled:
        raise HTTPException(status_code=404, detail="Documentation disabled")
    return JSONResponse(
        content={
            "status": "operational",
            "service": "Lex-Advisor Scraper API",
            "version": settings.service_version,
        },
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/v1/docs/health", status_code=status.HTTP_200_OK, include_in_schema=False)
async def docs_health_badge_v1() -> JSONResponse:
    return await docs_health_badge()
