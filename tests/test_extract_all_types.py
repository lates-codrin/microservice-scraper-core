# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for extraction endpoint with all 18 doc_types."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Extract test client."""
    app = create_app()
    return TestClient(app)


def test_extract_hcl_document(client):
    """POST /v1/extract extracts HCL fields."""
    hcl_content = """
    Hotărâre Consiliu Local nr. 42/2024
    adoptată în ședința din 15.03.2024
    privind aprobarea bugetului de venituri și cheltuieli
    pentru: 5
    împotrivă: 1
    abțineri: 0
    """

    response = client.post(
        "/v1/extract",
        json={
            "content": hcl_content,
            "doc_type": "hcl",
            "schema": {},
        },
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "test-tenant-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "fields" in data
    assert "field_confidence" in data


def test_extract_dispozitie_primar(client):
    """POST /v1/extract extracts Dispozitie fields."""
    content = "Disp. 15/2024 din data 01.04.2024"

    response = client.post(
        "/v1/extract",
        json={
            "content": content,
            "doc_type": "dispozitie_primar",
            "schema": {},
        },
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "test-tenant-2",
        },
    )

    assert response.status_code == 200


def test_extract_buget(client):
    """POST /v1/extract extracts Buget fields."""
    buget_content = """
    Bugetul local pentru anul 2024
    Venituri: 1.000.000 lei
    Cheltuieli: 950.000 RON
    """

    response = client.post(
        "/v1/extract",
        json={
            "content": buget_content,
            "doc_type": "buget",
            "schema": {},
        },
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "test-tenant-3",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "fields" in data


def test_extract_anunt_achizitie(client):
    """POST /v1/extract extracts Anunt Achizitie fields."""
    content = "Valoarea contractului: 50.000 lei"

    response = client.post(
        "/v1/extract",
        json={
            "content": content,
            "doc_type": "anunt_achizitie",
            "schema": {},
        },
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "test-tenant-4",
        },
    )

    assert response.status_code == 200


def test_extract_strategie(client):
    """POST /v1/extract extracts Strategie fields."""
    content = """
    Strategie de Dezvoltare 2024-2028
    Obiectiv 1: Îmbunătățirea infrastructurii
    Obiectiv 2: Creșterea economică
    Obiectiv 3: Dezvoltare socială
    """

    response = client.post(
        "/v1/extract",
        json={
            "content": content,
            "doc_type": "strategie",
            "schema": {},
        },
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "test-tenant-5",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "fields" in data


def test_extract_proces_verbal(client):
    """POST /v1/extract extracts Proces Verbal fields."""
    content = """
    Proces Verbal
    Punct 1: Hotărâre privind aprobarea contractului
    Punct 2: Decizie în privința achizițiilor
    Punct 3: Anunțul public de angajare
    """

    response = client.post(
        "/v1/extract",
        json={
            "content": content,
            "doc_type": "proces_verbal",
            "schema": {},
        },
        headers={
            "Authorization": "Bearer dev-api-key-change-me",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Tenant-ID": "test-tenant-6",
        },
    )

    assert response.status_code == 200


def test_extract_all_doctypes(client):
    """POST /v1/extract works for all 18 doc_types."""
    doc_types = [
        "hcl",
        "dispozitie_primar",
        "act_normativ_local",
        "proiect_hotarare",
        "regulament",
        "buget",
        "raport_executie_bugetara",
        "pug",
        "puz",
        "strategie",
        "organigrama",
        "raport_activitate",
        "proces_verbal",
        "consultare_publica",
        "anunt_public",
        "anunt_achizitie",
        "declaratie_avere",
        "other",
    ]

    test_content = "Test document content with some 2024 data"

    for doc_type in doc_types:
        response = client.post(
            "/v1/extract",
            json={
                "content": test_content,
                "doc_type": doc_type,
                "schema": {},
            },
            headers={
                "Authorization": "Bearer dev-api-key-change-me",
                "X-Request-ID": str(uuid.uuid4()),
                "X-Tenant-ID": f"test-tenant-all-{doc_type}",
            },
        )

        assert response.status_code == 200, f"Failed for doc_type: {doc_type}"
        data = response.json()
        assert "fields" in data
        assert "field_confidence" in data
        assert "missing_fields" in data
