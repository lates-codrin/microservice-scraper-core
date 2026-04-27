import schemathesis
import pytest
import uuid
from hypothesis import settings as hypothesis_settings, HealthCheck
from app.main import app
from app.settings import settings

# Load the schema
schema = schemathesis.from_path("scraper-api-spec.yaml", app=app)
schema.base_url = "/"

@pytest.fixture
def auth_headers():
    return {
        "Authorization": f"Bearer {settings.api_key}",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Tenant-ID": "test-tenant",
        "Idempotency-Key": str(uuid.uuid4())
    }

from unittest.mock import AsyncMock
from app.dependencies import get_job_store

@pytest.fixture(autouse=True)
def mock_dependencies():
    from app.models.crawl import CrawlJob, CrawlConfig, CrawlProgress, CrawlStats
    from datetime import datetime, timezone
    
    mock_store = AsyncMock()
    
    # Common return objects
    now = datetime.now(timezone.utc)
    mock_job = CrawlJob(
        job_id="cj_123",
        tenant_id="test-tenant",
        status="queued",
        config=CrawlConfig(seed_urls=["https://example.com"], allowed_domains=["example.com"]),
        submitted_at=now,
        progress=CrawlProgress(stage="queued", urls_discovered=0, urls_fetched=0, documents_extracted=0, documents_classified=0, urls_pending=0, bytes_downloaded=0),
        stats=CrawlStats(by_doc_type={}, http_errors={})
    )
    
    mock_store.queue_depth.return_value = 0
    mock_store.create_crawl_job.return_value = mock_job
    mock_store.get.return_value = mock_job
    mock_store.get_documents.return_value = ([], None, False, 0)
    mock_store.cancel_job.return_value = mock_job
    mock_store.delete.return_value = True
    mock_store.document_count.return_value = 0
    mock_store.create_scrape_job.return_value = "sj_123"
    
    app.dependency_overrides[get_job_store] = lambda: mock_store
    yield
    app.dependency_overrides.clear()

@schema.parametrize()
@hypothesis_settings(suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow], deadline=None)
def test_api_contract(case):
    # Add required headers to every request
    if case.headers is None:
        case.headers = {}
        
    case.headers.update({
        "Authorization": f"Bearer {settings.api_key}",
        "X-Request-ID": str(uuid.uuid4()),
        "X-Tenant-ID": "test-tenant",
    })
    
    # For endpoints requiring Idempotency-Key
    if case.method == "POST" and case.path in ["/v1/crawl", "/v1/scrape"]:
        case.headers["Idempotency-Key"] = str(uuid.uuid4())

    response = case.call_asgi()
    # Allow 501 Not Implemented for the optional extract endpoint
    if response.status_code == 501 and case.path == "/v1/extract":
        # Skip default checks which include not_server_error
        pass 
    else:
        case.validate_response(response)
    
    # Check for required headers echo
    assert response.headers.get("X-Request-ID") == case.headers.get("X-Request-ID")
    assert "RateLimit-Limit" in response.headers
    assert "RateLimit-Remaining" in response.headers
    assert "RateLimit-Reset" in response.headers
