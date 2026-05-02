"""Integration tests for POST /v1/extract — real field extractor through full stack."""

from __future__ import annotations

from tests.integration.conftest import _auth_headers


def test_extract_hcl_full_fields(client):
    resp = client.post(
        "/v1/extract",
        json={
            "content": (
                "Hotararea nr. 125/2024 privind aprobarea bugetului local. "
                "Data 15.03.2024. Pentru: 18, impotriva: 0, abtineri: 2"
            ),
            "doc_type": "hcl",
            "schema": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fields"]["hcl_number"] == "125/2024"
    assert body["fields"]["adoption_date"] == "2024-03-15"
    assert body["fields"]["subject"] == "aprobarea bugetului local"
    assert body["fields"]["votes"] == {"for": 18, "against": 0, "abstain": 2}
    assert "hcl_number" in body["field_confidence"]
    assert "adoption_date" in body["field_confidence"]
    assert body["missing_fields"] == []


def test_extract_hcl_partial_fields(client):
    resp = client.post(
        "/v1/extract",
        json={
            "content": "Hotararea nr. 42 din sedinta Consiliului Local.",
            "doc_type": "hcl",
            "schema": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fields"]["hcl_number"] is not None
    assert body["fields"]["adoption_date"] is None
    assert body["fields"]["subject"] is None
    assert body["fields"]["votes"] is None
    assert "adoption_date" in body["missing_fields"]


def test_extract_buget_fields(client):
    resp = client.post(
        "/v1/extract",
        json={
            "content": "Bugetul pentru anul 2024 prevede cheltuieli de 50 milioane lei.",
            "doc_type": "buget",
            "schema": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fields"]["budget_year"] == 2024
    assert body["fields"]["currency"] == "RON"


def test_extract_dispozitie_primar(client):
    resp = client.post(
        "/v1/extract",
        json={
            "content": "Dispozitie: 42/2024 privind convocarea in sedinta ordinara.",
            "doc_type": "dispozitie_primar",
            "schema": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fields"]["dispozitie_number"] == "42/2024"


def test_extract_other_doc_type_empty(client):
    resp = client.post(
        "/v1/extract",
        json={
            "content": "some text that does not match anything specific",
            "doc_type": "other",
            "schema": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fields"] == {}
    assert body["field_confidence"] == {}
    assert body["missing_fields"] == []


def test_extract_auth_required_401(client):
    resp = client.post(
        "/v1/extract",
        json={"content": "test", "doc_type": "hcl", "schema": {}},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_extract_response_structure(client):
    resp = client.post(
        "/v1/extract",
        json={
            "content": "Hotararea nr. 1/2024. Data 01.01.2024.",
            "doc_type": "hcl",
            "schema": {},
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "fields" in body
    assert "field_confidence" in body
    assert "missing_fields" in body
    assert isinstance(body["fields"], dict)
    assert isinstance(body["field_confidence"], dict)
    assert isinstance(body["missing_fields"], list)
