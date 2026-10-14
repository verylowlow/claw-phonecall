"""Tests for SIMCom backend classes (SIM800C, SIM7600)."""

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.backends.base import CallState


class FakeSerial:
    """Minimal serial port mock for testing AT command flow."""

    def __init__(self):
        self.is_open = True
        self.in_waiting = 0
        self._response_queue: list[bytes] = []
        self._written: list[bytes] = []

    def write(self, data: bytes) -> int:
        self._written.append(data)
        return len(data)

    def readline(self) -> bytes:
        if self._response_queue:
            return self._response_queue.pop(0)
        return b""

    def read(self, size: int) -> bytes:
        return b"\x80" * size

    def reset_input_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def queue_response(self, *lines: str) -> None:
        for line in lines:
            self._response_queue.append(f"{line}\r\n".encode("ascii"))


@pytest.fixture
def fake_serial():
    return FakeSerial()


def test_sim800c_inherits_simcom():
    from src.backends.sim800c import SIM800CBackend
    from src.backends.simcom_base import SIMComBackend
    assert issubclass(SIM800CBackend, SIMComBackend)
    assert SIM800CBackend._module_name == "SIM800C"


def test_sim7600_inherits_simcom():
    from src.backends.sim7600 import SIM7600Backend
    from src.backends.simcom_base import SIMComBackend
    assert issubclass(SIM7600Backend, SIMComBackend)
    assert SIM7600Backend._module_name == "SIM7600"


def test_sim800c_single_port():
    from src.backends.sim800c import SIM800CBackend
    b = SIM800CBackend("COM3")
    assert b._at_port == "COM3"
    assert b._audio_port == "COM3"


def test_sim7600_dual_port():
    from src.backends.sim7600 import SIM7600Backend
    b = SIM7600Backend("COM5", "COM6")
    assert b._at_port == "COM5"
    assert b._audio_port == "COM6"


def test_device_info():
    from src.backends.sim800c import SIM800CBackend
    b = SIM800CBackend("COM3", baud_rate=9600)
    info = b.device_info()
    assert info["type"] == "SIM800C"
    assert info["at_port"] == "COM3"
    assert info["baud"] == 9600
    assert info["healthy"] is False
    assert info["state"] == "IDLE"


@pytest.mark.asyncio
async def test_hangup_when_idle():
    from src.backends.sim800c import SIM800CBackend
    b = SIM800CBackend("COM3")
    result = await b.hangup()
    assert result is True
    assert b._state == CallState.IDLE


@pytest.mark.asyncio
async def test_read_audio_empty():
    from src.backends.sim7600 import SIM7600Backend
    b = SIM7600Backend("COM5", "COM6")
    data = await b.read_audio(160)
    assert data is None


@pytest.mark.asyncio
async def test_write_and_clear_playback():
    from src.backends.sim800c import SIM800CBackend
    b = SIM800CBackend("COM3")
    await b.write_audio(b"\x00" * 320)
    await b.write_audio(b"\x01" * 320)
    assert b._tx_queue.qsize() == 2
    await b.clear_playback()
    assert b._tx_queue.qsize() == 0


def test_handle_urc_voice_call_begin():
    from src.backends.simcom_base import SIMComBackend
    b = SIMComBackend.__new__(SIMComBackend)
    b._state = CallState.DIALING
    b._running = __import__("threading").Event()
    b._io_thread = None
    b._module_name = "Test"
    b._handle_urc("VOICE CALL: BEGIN")
    assert b._state == CallState.ACTIVE


def test_handle_urc_voice_call_end():
    from src.backends.simcom_base import SIMComBackend
    b = SIMComBackend.__new__(SIMComBackend)
    b._state = CallState.ACTIVE
    b._running = __import__("threading").Event()
    b._io_thread = None
    b._module_name = "Test"
    b._handle_urc("VOICE CALL: END")
    assert b._state == CallState.IDLE


def test_handle_urc_ring():
    from src.backends.simcom_base import SIMComBackend
    b = SIMComBackend.__new__(SIMComBackend)
    b._state = CallState.IDLE
    b._running = __import__("threading").Event()
    b._io_thread = None
    b._module_name = "Test"
    b._handle_urc("RING")
    assert b._state == CallState.RINGING
