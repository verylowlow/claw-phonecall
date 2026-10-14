"""
SIMCom GSM/LTE module base backend — shared AT command logic for SIM800C / SIM7600.

Both modules use the same core AT command set for voice calls:
  ATD<number>;  — dial (voice call, the ; suffix is required)
  ATA           — answer incoming call
  ATH           — hang up
  AT+CPCMREG=1  — enable PCM audio over serial/USB
  AT+CPCMREG=0  — disable PCM audio

Audio format: 8kHz, 16-bit signed LE, mono PCM.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Optional

from .base import TelephonyBackend, CallState

logger = logging.getLogger(__name__)

_DEFAULT_BAUD = 115200
_AT_TIMEOUT = 5.0
_DIAL_TIMEOUT = 45.0
_PCM_CHUNK_BYTES = 320  # 20ms of 8kHz 16-bit mono


class SIMComBackend(TelephonyBackend):
    """
    Base backend for SIMCom cellular modules (SIM800C, SIM7600, etc.).
    Subclasses set `_module_name` and override `_init_module()`.
    """

    _module_name: str = "SIMCom"

    def __init__(
        self,
        at_port: str,
        audio_port: Optional[str] = None,
        baud_rate: int = _DEFAULT_BAUD,
    ):
        self._at_port = at_port
        self._audio_port = audio_port or at_port
        self._baud = baud_rate
        self._at_serial = None
        self._audio_serial = None
        self._state = CallState.IDLE
        self._healthy = False

        self._rx_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self._tx_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self._io_thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._urc_thread: Optional[threading.Thread] = None
        self._urc_running = threading.Event()

    # ── lifecycle ──

    async def initialize(self) -> None:
        import serial
        try:
            self._at_serial = serial.Serial(
                self._at_port, self._baud, timeout=1, write_timeout=1
            )
            if self._audio_port != self._at_port:
                self._audio_serial = serial.Serial(
                    self._audio_port, self._baud, timeout=1, write_timeout=1
                )
            else:
                self._audio_serial = self._at_serial

            resp = await self._at_cmd("AT")
            if "OK" not in resp:
                raise RuntimeError(f"{self._module_name} not responding on {self._at_port}")

            await self._at_cmd("ATE0")
            await self._at_cmd("ATZ")
            await asyncio.sleep(0.5)

            await self._init_module()

            resp = await self._at_cmd("AT+CPIN?")
            if "READY" not in resp:
                raise RuntimeError(f"SIM card not ready: {resp}")

            csq = await self._at_cmd("AT+CSQ")
            logger.info("%s signal quality: %s", self._module_name, csq.strip())

            self._healthy = True
            self._start_urc_monitor()
            logger.info(
                "%s initialized on AT=%s Audio=%s @ %d baud",
                self._module_name, self._at_port, self._audio_port, self._baud,
            )
        except Exception:
            self._healthy = False
            logger.exception("Failed to initialize %s on %s", self._module_name, self._at_port)
            raise

    async def _init_module(self) -> None:
        """Subclass hook for module-specific AT init sequence."""

    async def shutdown(self) -> None:
        self._stop_voice_io()
        self._stop_urc_monitor()
        await self._disable_pcm()
        closed: set[int] = set()
        for ser in (self._audio_serial, self._at_serial):
            if ser and ser.is_open and id(ser) not in closed:
                closed.add(id(ser))
                try:
                    ser.write(b"ATH\r\n")
                    ser.close()
                except Exception:
                    pass
        self._at_serial = None
        self._audio_serial = None
        self._healthy = False
        logger.info("[%s] Shutdown complete", self._module_name)

    # ── call control ──

    async def dial(self, number: str) -> bool:
        if not self._at_serial:
            return False
        number = number.strip().replace(" ", "").replace("-", "")
        try:
            self._state = CallState.DIALING
            await self._at_cmd(f"ATD{number};", timeout=_DIAL_TIMEOUT)

            if await self._wait_for_connect(timeout=30):
                self._state = CallState.ACTIVE
                await self._enable_pcm()
                self._start_voice_io()
                logger.info("[%s] Call connected to %s", self._module_name, number)
                return True

            logger.warning("[%s] Dial timeout / rejected for %s", self._module_name, number)
            self._state = CallState.IDLE
            await self._at_cmd("ATH")
            return False
        except Exception:
            logger.exception("[%s] Dial error for %s", self._module_name, number)
            self._state = CallState.IDLE
            return False

    async def _wait_for_connect(self, timeout: float = 30) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._state == CallState.ACTIVE:
                return True
            if self._state == CallState.IDLE:
                return False
            await asyncio.sleep(0.3)
        return False

    async def answer(self) -> bool:
        if not self._at_serial:
            return False
        try:
            resp = await self._at_cmd("ATA")
            if "OK" in resp or "CONNECT" in resp:
                self._state = CallState.ACTIVE
                await self._enable_pcm()
                self._start_voice_io()
                return True
            return False
        except Exception:
            logger.exception("[%s] Answer failed", self._module_name)
            return False

    async def hangup(self) -> bool:
        self._stop_voice_io()
        await self._disable_pcm()
        if not self._at_serial:
            self._state = CallState.IDLE
            return True
        try:
            await self._at_cmd("ATH")
            self._state = CallState.IDLE
            return True
        except Exception:
            logger.exception("[%s] Hangup error", self._module_name)
            self._state = CallState.IDLE
            return True

    # ── audio I/O ──

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

    # ── state ──

    async def get_state(self) -> CallState:
        return self._state

    def is_healthy(self) -> bool:
        return self._healthy and self._at_serial is not None and self._at_serial.is_open

    def device_info(self) -> dict:
        return {
            "type": self._module_name,
            "at_port": self._at_port,
            "audio_port": self._audio_port,
            "baud": self._baud,
            "healthy": self.is_healthy(),
            "state": self._state.name,
            "device_id": self._at_port,
        }

    # ── AT command helpers ──

    async def _at_cmd(self, cmd: str, timeout: float = _AT_TIMEOUT) -> str:
        if not self._at_serial or not self._at_serial.is_open:
            return ""

        def _do() -> str:
            self._at_serial.reset_input_buffer()
            self._at_serial.write(f"{cmd}\r\n".encode("ascii"))
            lines: list[str] = []
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                raw = self._at_serial.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                lines.append(line)
                if any(kw in line for kw in (
                    "OK", "ERROR", "CONNECT", "BUSY",
                    "NO CARRIER", "NO ANSWER", "NO DIALTONE",
                )):
                    break
            return "\n".join(lines)

        return await asyncio.to_thread(_do)

    async def _enable_pcm(self) -> None:
        resp = await self._at_cmd("AT+CPCMREG=1")
        if "OK" in resp:
            logger.debug("[%s] PCM audio enabled", self._module_name)
        else:
            logger.warning("[%s] PCM enable response: %s", self._module_name, resp)

    async def _disable_pcm(self) -> None:
        if self._at_serial and self._at_serial.is_open:
            try:
                await self._at_cmd("AT+CPCMREG=0")
            except Exception:
                pass

    # ── URC (Unsolicited Result Code) monitor ──

    def _start_urc_monitor(self) -> None:
        if self._urc_running.is_set():
            return
        if self._audio_port == self._at_port:
            return
        self._urc_running.set()
        self._urc_thread = threading.Thread(target=self._urc_loop, daemon=True)
        self._urc_thread.start()

    def _stop_urc_monitor(self) -> None:
        self._urc_running.clear()
        if self._urc_thread:
            self._urc_thread.join(timeout=2)
            self._urc_thread = None

    def _urc_loop(self) -> None:
        while self._urc_running.is_set():
            if not self._at_serial or not self._at_serial.is_open:
                break
            try:
                if self._at_serial.in_waiting > 0:
                    line = self._at_serial.readline().decode("ascii", errors="replace").strip()
                    if line:
                        self._handle_urc(line)
                else:
                    time.sleep(0.05)
            except Exception:
                break

    def _handle_urc(self, line: str) -> None:
        upper = line.upper()
        if "VOICE CALL: BEGIN" in upper:
            logger.info("[%s] URC: Call connected", self._module_name)
            self._state = CallState.ACTIVE
        elif "VOICE CALL: END" in upper:
            logger.info("[%s] URC: Call ended", self._module_name)
            self._state = CallState.IDLE
            self._stop_voice_io()
        elif "RING" in upper:
            logger.info("[%s] URC: Incoming call", self._module_name)
            self._state = CallState.RINGING
        elif "NO CARRIER" in upper or "BUSY" in upper:
            self._state = CallState.IDLE

    # ── PCM voice I/O thread ──

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
        ser = self._audio_serial
        if not ser:
            return

        logger.debug("[%s] Voice I/O loop started", self._module_name)
        while self._running.is_set():
            try:
                if ser.in_waiting > 0:
                    data = ser.read(min(ser.in_waiting, _PCM_CHUNK_BYTES))
                    if data:
                        try:
                            self._rx_queue.put_nowait(data)
                        except queue.Full:
                            pass

                try:
                    tx_data = self._tx_queue.get_nowait()
                    ser.write(tx_data)
                except queue.Empty:
                    pass

                if ser.in_waiting == 0 and self._tx_queue.empty():
                    time.sleep(0.005)
            except Exception:
                logger.exception("[%s] Voice I/O error", self._module_name)
                break

        logger.debug("[%s] Voice I/O loop ended", self._module_name)
