"""Integration tests for POST /v1/classify — real classifier through full stack."""

from __future__ import annotations

from tests.integration.conftest import _auth_headers


def test_classify_hcl_url_plus_text_confidence_094(client):
    resp = client.post(
        "/v1/classify",
        json={
            "content": "Hotararea nr. 125 privind aprobarea bugetului local pe anul 2024.",
            "url_hint": "https://primaria-exemplu.ro/hcl/125",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_type"] == "hcl"
    assert body["doc_type_confidence"] == 0.94
    assert body["language"] == "ro"
    assert isinstance(body["alternatives"], list)


def test_classify_buget_text_only_confidence_080(client):
    resp = client.post(
        "/v1/classify",
        json={
            "content": "Bugetul local al municipiului pentru anul 2024 prevede venituri totale de 125 milioane lei.",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_type"] == "buget"
    assert body["doc_type_confidence"] == 0.80


def test_classify_url_only_confidence_075(client):
    resp = client.post(
        "/v1/classify",
        json={
            "content": "lorem ipsum dolor sit amet consectetur adipiscing elit",
            "url_hint": "https://primaria-exemplu.ro/dispozitii/42",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_type"] == "dispozitie_primar"
    assert body["doc_type_confidence"] == 0.75


def test_classify_no_match_returns_other(client):
    resp = client.post(
        "/v1/classify",
        json={
            "content": "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_type"] == "other"
    assert body["doc_type_confidence"] == 0.40
    assert body["alternatives"] == []


def test_classify_auth_required_401(client):
    resp = client.post(
        "/v1/classify",
        json={"content": "test content"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_classify_response_structure(client):
    resp = client.post(
        "/v1/classify",
        json={
            "content": "Hotararea nr. 125 privind aprobarea bugetului.",
            "url_hint": "https://primaria-exemplu.ro/hcl/125",
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "doc_type" in body
    assert "doc_type_confidence" in body
    assert "language" in body
    assert "alternatives" in body
    assert isinstance(body["doc_type"], str)
    assert isinstance(body["doc_type_confidence"], float)
    assert 0.0 <= body["doc_type_confidence"] <= 1.0
    assert isinstance(body["alternatives"], list)
    for alt in body["alternatives"]:
        assert "doc_type" in alt
        assert "confidence" in alt
