import uuid

from locust import HttpUser, between, task


class ScraperUser(HttpUser):
    wait_time = between(5, 5)

    @task(3)
    def poll_job(self):
        self.client.get(
            "/v1/jobs/cj_loadtest123",
            name="/v1/jobs/{job_id}",
            headers={
                "Authorization": "Bearer dev-api-key-change-me",
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": "load-tenant",
            },
        )

    @task(1)
    def fetch_documents(self):
        self.client.get(
            "/v1/jobs/cj_loadtest123/documents?limit=100",
            name="/v1/jobs/{job_id}/documents",
            headers={
                "Authorization": "Bearer dev-api-key-change-me",
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": "load-tenant",
            },
        )
