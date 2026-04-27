from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_docs_scalar_returns_200_when_enabled(client: TestClient) -> None:
    """Test that /docs returns 200 and contains Scalar JS bundle when DOCS_ENABLED=true."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    # Verify Scalar JS bundle is referenced
    assert "scalar/api-reference" in response.text or "Scalar" in response.text


def test_docs_redoc_returns_200_when_enabled(client: TestClient) -> None:
    """Test that /redoc returns 200 and contains ReDoc bundle when DOCS_ENABLED=true."""
    response = client.get("/redoc")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    # Verify ReDoc JS bundle is referenced
    assert "redoc" in response.text.lower()


def test_docs_health_badge_returns_service_status(client: TestClient) -> None:
    """Test that /docs/health returns operational status for Scalar sidebar badge."""
    response = client.get("/docs/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "operational"
    assert data["service"] == "Lex-Advisor Scraper API"
    assert data["version"] == settings.service_version
    assert response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"


def test_openapi_json_returns_valid_spec(client: TestClient) -> None:
    """Test that /v1/openapi.json returns valid JSON OpenAPI spec."""
    response = client.get("/v1/openapi.json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    
    spec = response.json()
    assert isinstance(spec, dict)
    assert spec.get("openapi") == "3.0.3"
    assert spec.get("info", {}).get("title") == "Lex-Advisor Scraper Service API"
    assert "paths" in spec
    assert "components" in spec
    # Verify x-scalar-theme is present
    assert spec.get("info", {}).get("x-scalar-theme") == "purple"


def test_openapi_spec_has_examples(client: TestClient) -> None:
    """Test that OpenAPI spec includes examples for key endpoints."""
    response = client.get("/v1/openapi.json")
    spec = response.json()
    
    # Verify POST /v1/scrape has example and code samples
    scrape_post = spec["paths"]["/v1/scrape"]["post"]
    assert "requestBody" in scrape_post
    assert "example" in scrape_post["requestBody"]["content"]["application/json"]
    assert "x-codeSamples" in scrape_post
    
    scrape_samples = scrape_post["x-codeSamples"]
    assert len(scrape_samples) >= 3  # curl, python, javascript
    scrape_langs = {sample["lang"] for sample in scrape_samples}
    assert "curl" in scrape_langs
    assert "python" in scrape_langs
    assert "javascript" in scrape_langs
    
    # Verify POST /v1/crawl has example and code samples
    crawl_post = spec["paths"]["/v1/crawl"]["post"]
    assert "requestBody" in crawl_post
    assert "example" in crawl_post["requestBody"]["content"]["application/json"]
    assert "x-codeSamples" in crawl_post
    
    crawl_samples = crawl_post["x-codeSamples"]
    assert len(crawl_samples) >= 3  # curl, python, javascript
    crawl_langs = {sample["lang"] for sample in crawl_samples}
    assert "curl" in crawl_langs
    assert "python" in crawl_langs
    assert "javascript" in crawl_langs


def test_openapi_spec_has_parameter_descriptions(client: TestClient) -> None:
    """Test that query parameters have proper descriptions."""
    response = client.get("/v1/openapi.json")
    spec = response.json()
    
    # Verify /v1/jobs/{job_id}/documents parameters have descriptions
    docs_get = spec["paths"]["/v1/jobs/{job_id}/documents"]["get"]

    def resolve_param(param: dict) -> dict:
        ref = param.get("$ref")
        if not ref:
            return param
        key = ref.split("/")[-1]
        return spec["components"]["parameters"][key]

    resolved_params = [resolve_param(p) for p in docs_get["parameters"]]
    params_by_name = {p["name"]: p for p in resolved_params}
    
    assert "description" in params_by_name["cursor"]
    assert "pagination token" in params_by_name["cursor"]["description"].lower()
    
    assert "description" in params_by_name["limit"]
    assert "description" in params_by_name["doc_type"]
    assert "Filter by classification" in params_by_name["doc_type"]["description"]
    
    assert "description" in params_by_name["min_confidence"]
    assert "confidence" in params_by_name["min_confidence"]["description"].lower()


def test_scalar_docs_references_correct_spec_url() -> None:
    """Test that Scalar docs HTML references the correct OpenAPI spec URL."""
    from app.routers.docs import _get_scalar_html
    
    html = _get_scalar_html("/v1/openapi.json")
    assert "/v1/openapi.json" in html
    assert "api-reference" in html
    assert "scalar" in html.lower()
    assert "purple" in html  # theme


def test_redoc_docs_references_correct_spec_url() -> None:
    """Test that ReDoc docs HTML references the correct OpenAPI spec URL."""
    from app.routers.docs import _get_redoc_html
    
    html = _get_redoc_html("/v1/openapi.json")
    assert "/v1/openapi.json" in html
    assert "redoc" in html.lower()
