"""Tests for the Twilio-compatible REST API layer."""

from unittest.mock import patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.twilio_compat.rest_api import router


@pytest.fixture
def client():
    test_app = FastAPI()
    with patch("src.twilio_compat.rest_api.initiate_call", new_callable=AsyncMock):
        test_app.include_router(router)
        with TestClient(test_app) as c:
            yield c


def test_create_call(client):
    resp = client.post(
        "/2010-04-01/Accounts/LOCAL_BRIDGE/Calls.json",
        data={"To": "+8613800001111", "From": "+8610000000", "Url": "http://localhost/twiml"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sid"].startswith("CA")
    assert body["status"] == "queued"
    assert body["to"] == "+8613800001111"


def test_update_call_not_found(client):
    resp = client.post(
        "/2010-04-01/Accounts/LOCAL_BRIDGE/Calls/CA_nonexistent.json",
        data={"Status": "completed"},
    )
    assert resp.status_code == 404
