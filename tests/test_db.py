"""Tests for database models."""

import pytest
from src.db import models


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Each test gets its own fresh database."""
    db_path = tmp_path / "test.db"
    original = models._db_path
    models._db_path = db_path
    if hasattr(models._local, "conn"):
        models._local.conn = None
    models.init_db()
    yield
    if hasattr(models._local, "conn") and models._local.conn:
        models._local.conn.close()
        models._local.conn = None
    models._db_path = original


def test_db_operations():
    row_id = models.insert_call(
        call_sid="CA_test_001",
        phone_number="+8613800001111",
        direction="outbound",
        backend_type="mock",
    )
    assert row_id > 0

    call = models.get_call("CA_test_001")
    assert call is not None
    assert call["phone_number"] == "+8613800001111"
    assert call["status"] == "initiated"

    models.update_call("CA_test_001", status="in-progress")
    call = models.get_call("CA_test_001")
    assert call["status"] == "in-progress"

    models.complete_call("CA_test_001", 120, "/tmp/test.wav")
    call = models.get_call("CA_test_001")
    assert call["status"] == "completed"
    assert call["duration"] == 120

    calls = models.list_calls(phone_number="138")
    assert len(calls) == 1

    calls = models.list_calls(phone_number="999")
    assert len(calls) == 0

    count = models.count_calls()
    assert count == 1


def test_dashboard_stats():
    models.insert_call("CA_s1", "+861", backend_type="mock")
    models.insert_call("CA_s2", "+862", backend_type="mock")
    models.complete_call("CA_s1", 60)

    stats = models.get_dashboard_stats()
    assert stats["total_calls"] == 2
    assert len(stats["recent_calls"]) == 2


def test_device_upsert():
    models.upsert_device("mock", "default", "online")
    devices = models.list_devices()
    assert len(devices) == 1
    assert devices[0]["status"] == "online"

    models.upsert_device("mock", "default", "offline")
    devices = models.list_devices()
    assert len(devices) == 1
    assert devices[0]["status"] == "offline"
