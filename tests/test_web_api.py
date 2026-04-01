"""Tests for the web management API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.db import models
from src.web.api import router as web_router


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    original = models._db_path
    models._db_path = db_path
    if hasattr(models._local, "conn"):
        models._local.conn = None
    models.init_db()

    models.insert_call("CA_web1", "+8613800001111", backend_type="mock")
    models.complete_call("CA_web1", 90, str(tmp_path / "test.wav"))
    (tmp_path / "test.wav").write_bytes(b"\x00" * 100)

    test_app = FastAPI()
    test_app.include_router(web_router)
    with TestClient(test_app) as c:
        yield c

    if hasattr(models._local, "conn") and models._local.conn:
        models._local.conn.close()
        models._local.conn = None
    models._db_path = original


def test_dashboard(client):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_calls" in data
    assert "devices" in data


def test_list_calls(client):
    resp = client.get("/api/calls")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


def test_get_call(client):
    resp = client.get("/api/calls/CA_web1")
    assert resp.status_code == 200
    assert resp.json()["phone_number"] == "+8613800001111"


def test_get_call_not_found(client):
    resp = client.get("/api/calls/CA_nonexistent")
    assert resp.status_code == 404
