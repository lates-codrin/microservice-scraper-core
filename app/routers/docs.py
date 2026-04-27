from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.main import app as fastapi_app
from app.settings import settings

router = APIRouter(tags=["docs"])


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
            * {{
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background: #0f1419;
                color: #fff;
            }}
        </style>
    </head>
    <body>
        <script id="api-reference" data-url="{spec_url}" data-configuration='{{"theme":"purple","hideDownloadButton":false}}' src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
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
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: #fafafa;
            }}
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


@router.get("/redoc", response_class=HTMLResponse, include_in_schema=False)
async def get_redoc_docs() -> str:
    """Serve read-only ReDoc API documentation."""
    if not settings.docs_enabled:
        raise HTTPException(status_code=404, detail="Documentation disabled")
    
    return _get_redoc_html("/v1/openapi.json")


@router.get("/docs/health", status_code=status.HTTP_200_OK, include_in_schema=False)
async def docs_health_badge() -> JSONResponse:
    """Health check endpoint for Scalar sidebar status badge.
    
    Returns basic service status that Scalar can ping to show live server status.
    """
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
