"""
USB Voice Modem backend — control a phone line via AT commands over serial.

Typical hardware: USR5637, Conexant CX93001, or similar voice modem.
Connection: phone line (RJ11) -> modem -> USB -> PC.

AT command flow:
  ATZ          — reset
  AT+FCLASS=8  — enter voice mode
  AT+VLS=1     — switch to phone line
  ATDT<number> — dial DTMF
  ATH1         — go off-hook
  ATH0         — hang up
  AT+VRX       — start receiving voice data
  AT+VTX       — start transmitting voice data
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Optional

from .base import TelephonyBackend, CallState

logger = logging.getLogger(__name__)

_DEFAULT_BAUD = 115200
_AT_TIMEOUT = 3.0


class USBModemBackend(TelephonyBackend):
    """Telephony backend using a USB voice modem via serial/AT commands."""

    def __init__(self, port: str, baud_rate: int = _DEFAULT_BAUD):
        self._port = port
        self._baud = baud_rate
        self._serial = None
        self._state = CallState.IDLE
        self._healthy = False
        self._rx_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self._tx_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self._io_thread: Optional[threading.Thread] = None
        self._running = threading.Event()

    async def initialize(self) -> None:
        import serial
        try:
            self._serial = serial.Serial(
                self._port, self._baud, timeout=1, write_timeout=1
            )
            resp = await self._at_cmd("ATZ")
            if "OK" not in resp:
                raise RuntimeError(f"Modem reset failed: {resp}")

            await self._at_cmd("ATE0")
            resp = await self._at_cmd("AT+FCLASS=8")
            if "OK" not in resp:
                raise RuntimeError(f"Voice mode not supported: {resp}")

            self._healthy = True
            logger.info("USB modem initialized on %s @ %d baud", self._port, self._baud)
        except Exception:
            self._healthy = False
            logger.exception("Failed to initialize USB modem on %s", self._port)
            raise

    async def dial(self, number: str) -> bool:
        if not self._serial:
            return False
        try:
            await self._at_cmd("AT+VLS=1")
            await self._at_cmd("ATH1")
            self._state = CallState.DIALING

            resp = await self._at_cmd(f"ATDT{number}", timeout=30)
            if "OK" in resp or "CONNECT" in resp:
                self._state = CallState.ACTIVE
                self._start_voice_io()
                logger.info("Modem call connected to %s", number)
                return True

            if "BUSY" in resp:
                logger.warning("Line busy for %s", number)
            elif "NO CARRIER" in resp or "NO ANSWER" in resp:
                logger.warning("No answer for %s: %s", number, resp)
            else:
                logger.warning("Dial failed for %s: %s", number, resp)

            self._state = CallState.IDLE
            await self._at_cmd("ATH0")
            return False
        except Exception:
            logger.exception("Dial error for %s", number)
            self._state = CallState.IDLE
            return False

    async def answer(self) -> bool:
        if not self._serial:
            return False
        try:
            await self._at_cmd("ATH1")
            self._state = CallState.ACTIVE
            self._start_voice_io()
            return True
        except Exception:
            logger.exception("Answer failed")
            return False

    async def hangup(self) -> bool:
        self._stop_voice_io()
        if not self._serial:
            self._state = CallState.IDLE
            return True
        try:
            if self._serial.is_open:
                self._serial.write(b"\x10\x03")
                await asyncio.sleep(0.2)
                await self._at_cmd("ATH0")
            self._state = CallState.IDLE
            return True
        except Exception:
            logger.exception("Hangup error")
            self._state = CallState.IDLE
            return True

    async def read_audio(self, num_samples: int) -> Optional[bytes]:
        try:
            return self._rx_queue.get_nowait()
        except queue.Empty:
            return None

    async def write_audio(self, data: bytes) -> None:
        try:
            self._tx_queue.put_nowait(data)
        except queue.Full:
            pass

    async def clear_playback(self) -> None:
        while not self._tx_queue.empty():
            try:
                self._tx_queue.get_nowait()
            except queue.Empty:
                break

    async def get_state(self) -> CallState:
        return self._state

    def is_healthy(self) -> bool:
        return self._healthy and self._serial is not None and self._serial.is_open

    async def shutdown(self) -> None:
        self._stop_voice_io()
        if self._serial and self._serial.is_open:
            try:
                self._serial.write(b"ATH0\r\n")
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._healthy = False
        logger.info("USB modem shutdown")

    def device_info(self) -> dict:
        return {
            "type": "USBModemBackend",
            "port": self._port,
            "baud": self._baud,
            "healthy": self.is_healthy(),
            "state": self._state.name,
        }

    async def _at_cmd(self, cmd: str, timeout: float = _AT_TIMEOUT) -> str:
        if not self._serial or not self._serial.is_open:
            return ""

        def _do() -> str:
            self._serial.reset_input_buffer()
            self._serial.write(f"{cmd}\r\n".encode("ascii"))
            lines = []
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                line = self._serial.readline().decode("ascii", errors="replace").strip()
                if line:
                    lines.append(line)
                if any(r in line for r in ("OK", "ERROR", "CONNECT", "BUSY", "NO CARRIER", "NO ANSWER")):
                    break
            return "\n".join(lines)

        return await asyncio.to_thread(_do)

    def _start_voice_io(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self._io_thread = threading.Thread(target=self._voice_io_loop, daemon=True)
        self._io_thread.start()

    def _stop_voice_io(self) -> None:
        self._running.clear()
        if self._io_thread:
            self._io_thread.join(timeout=2)
            self._io_thread = None

    def _voice_io_loop(self) -> None:
        """Blocking I/O loop for voice data exchange with the modem."""
        if not self._serial:
            return

        try:
            self._serial.write(b"AT+VRX\r\n")
        except Exception:
            return

        while self._running.is_set():
            try:
                if self._serial.in_waiting > 0:
                    data = self._serial.read(min(self._serial.in_waiting, 320))
                    if data:
                        try:
                            self._rx_queue.put_nowait(data)
                        except queue.Full:
                            pass

                try:
                    tx_data = self._tx_queue.get_nowait()
                    self._serial.write(tx_data)
                except queue.Empty:
                    pass

                if self._serial.in_waiting == 0 and self._tx_queue.empty():
                    import time
                    time.sleep(0.005)
            except Exception:
                logger.exception("Voice I/O error")
                break
