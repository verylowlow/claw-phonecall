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
# 收到命令结束行后，继续读这么久以收集随后到达的 URC。
# ATD 是异步的：先回 OK 表示「命令已接受」，真正的接通结果稍后才以
# VOICE CALL: BEGIN 上报。这个窗口就是为它留的。
_URC_DRAIN_S = 0.5

# 模块主动上报的行（URC）。它们出现在命令等待期间，不是任何一条命令的回应。
# 注意：BUSY / NO CARRIER / NO ANSWER / NO DIALTONE 虽然也可能作为 URC 出现，
# 但它们同时是命令的**结果码**—— 必须回给调用方判断呼叫是否失败，
# 所以只把「明确是通话状态变化」的行放进这个表。
_URC_PREFIXES = (
    "VOICE CALL:", "+CLIP", "RING", "RINGING", "CALL READY",
)


def _looks_like_urc(line: str) -> bool:
    upper = line.upper()
    if upper in ("OK", "ERROR"):
        return False
    return any(upper.startswith(p) for p in _URC_PREFIXES)


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
        # pyserial 对象不是线程安全的：URC 线程与 AT 命令线程会争抢同一个口。
        # 所有串口读写都必须经过这把锁，否则回应行会被对方读走。
        self._serial_lock = threading.RLock()
        # 拨号后到达的 URC（例如 VOICE CALL: BEGIN）可能早于 ATD 的最终回显，
        # 单靠 URC 线程会漏事件，这里缓存起来供 _wait_for_connect 复查。
        self._pending_urc: list[str] = []

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
            resp = await self._at_cmd(
                f"ATD{number};", timeout=_DIAL_TIMEOUT, drain_urc=True
            )

            # 明确失败（忙线/无应答/无拨号音）要立刻返回，
            # 否则会白等 _wait_for_connect 的 30 秒。
            if any(k in resp for k in ("BUSY", "NO ANSWER", "NO DIALTONE")):
                logger.warning("[%s] Dial rejected for %s: %s",
                               self._module_name, number, resp)
                self._state = CallState.IDLE
                return False

            if not await self._wait_for_connect(timeout=30):
                logger.warning("[%s] Dial timeout for %s", self._module_name, number)
                self._state = CallState.IDLE
                await self._at_cmd("ATH")
                return False

            self._state = CallState.ACTIVE
            # PCM 通路没打开就等于静音通话，必须挂断而不是假装接通，
            # 否则对端听着"接通但没声音"，比响铃失败更难排查。
            if not await self._enable_pcm():
                logger.error("[%s] PCM enable failed, dropping call to %s",
                             self._module_name, number)
                self._state = CallState.IDLE
                await self._at_cmd("ATH")
                return False
            self._start_voice_io()
            logger.info("[%s] Call connected to %s", self._module_name, number)
            return True
        except Exception:
            logger.exception("[%s] Dial error for %s", self._module_name, number)
            self._state = CallState.IDLE
            return False

    async def _wait_for_connect(self, timeout: float = 30) -> bool:
        """等待通话接通。

        除了看 _state，还要复查 _pending_urc：SIM800C 这类单口模块不会启动
        URC 线程（口被 AT 命令与音频共用，另起线程只会与 _at_cmd 争抢），
        此时接通事件只能从 ATD 的回显里读出来。
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._state == CallState.ACTIVE:
                return True
            if self._state == CallState.IDLE:
                return False
            with self._serial_lock:
                pending, self._pending_urc = self._pending_urc, []
            for line in pending:
                self._handle_urc(line)
            if self._state == CallState.ACTIVE:
                return True
            await asyncio.sleep(0.3)
        return False

    async def answer(self) -> bool:
        if not self._at_serial:
            return False
        try:
            resp = await self._at_cmd("ATA")
            if "OK" in resp or "CONNECT" in resp:
                self._state = CallState.ACTIVE
                if not await self._enable_pcm():
                    logger.error("[%s] Answered but PCM enable failed", self._module_name)
                    self._state = CallState.IDLE
                    await self._at_cmd("ATH")
                    return False
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
            resp = await self._at_cmd("ATH")
            # ATH 只是「请求挂断」，模块回 OK 不代表对端已释放线路。
            # 回 NO CARRIER 才说明通话真正结束，所以两者都算成功，
            # 其它错误必须上报失败，否则 bridge 会一直以为已挂断。
            ok = any(k in resp for k in ("OK", "NO CARRIER"))
            if not ok:
                logger.warning("[%s] ATH unexpected response: %s", self._module_name, resp)
            self._state = CallState.IDLE
            return ok
        except Exception:
            logger.exception("[%s] Hangup error", self._module_name)
            self._state = CallState.IDLE
            return False

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

    async def _at_cmd(self, cmd: str, timeout: float = _AT_TIMEOUT,
                      drain_urc: bool = True) -> str:
        """下发一条 AT 命令并收集回应。

        drain_urc=False 时收到结束行立刻返回——用于拨号：
        BUSY / NO ANSWER 这类结果码本身就是呼叫结论，没必要再等 URC。
        """
        if not self._at_serial or not self._at_serial.is_open:
            return ""

        def _do() -> str:
            # 整段读写必须持锁：URC 线程可能正在同一个口上读，
            # 不加锁时 ATD 的回应行会被它读走，导致命令「无响应」。
            urc: list[str] = []
            drain_s = _URC_DRAIN_S if drain_urc else 0.0
            with self._serial_lock:
                self._at_serial.reset_input_buffer()
                self._at_serial.write(f"{cmd}\r\n".encode("ascii"))
                lines: list[str] = []
                end = time.monotonic() + timeout
                terminated_at: Optional[float] = None
                while time.monotonic() < end:
                    raw = self._at_serial.readline()
                    if not raw:
                        # 收到结束行后再给一小段窗口收URC：
                        # ATD 是「先回 OK（命令已接受），稍后才报VOICE CALL: BEGIN」，
                        # 在 OK 上立刻 break 就永远读不到接通事件，表现为拨不通。
                        if terminated_at is not None and (
                            time.monotonic() - terminated_at >= drain_s
                        ):
                            break
                        continue
                    line = raw.decode("ascii", errors="replace").strip()
                    if not line:
                        continue
                    if _looks_like_urc(line):
                        # URC 不作为命令的结束标记，单独收走
                        urc.append(line)
                        continue
                    lines.append(line)
                    if any(kw in line for kw in (
                        "OK", "ERROR", "CONNECT", "BUSY",
                        "NO CARRIER", "NO ANSWER", "NO DIALTONE",
                    )):
                        terminated_at = time.monotonic()
                # 短窗内没有新行则尽快收尾
                if terminated_at is not None and drain_s > 0:
                    deadline = terminated_at + drain_s
                    while time.monotonic() < deadline:
                        raw = self._at_serial.readline()
                        if not raw:
                            continue
                        line = raw.decode("ascii", errors="replace").strip()
                        if line and _looks_like_urc(line):
                            urc.append(line)
            self._pending_urc.extend(urc)
            for line in urc:
                self._handle_urc(line)
            return "\n".join(x for x in lines if x)

        return await asyncio.to_thread(_do)

    async def _enable_pcm(self) -> bool:
        """使能 PCM 音频通路。返回是否成功——失败必须让调用方知道，
        否则会在没有音频通路的通话上白等30 秒。"""
        resp = await self._at_cmd("AT+CPCMREG=1")
        if "OK" in resp:
            logger.debug("[%s] PCM audio enabled", self._module_name)
            return True
        logger.warning("[%s] PCM enable failed: %s", self._module_name, resp)
        return False

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
        # 单口模块（SIM800C）不另起 URC 线程：这个口已经被 _at_cmd 与音频
        # I/O 占满，再加一个读者只会三方争抢。接通事件改由 _at_cmd 从命令
        # 回显里摘出，写进 _pending_urc 供 _wait_for_connect 复查。
        if self._audio_port == self._at_port:
            logger.debug(
                "[%s] single-port module, URC handled inline via _at_cmd",
                self._module_name,
            )
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
                # 必须持锁：否则本线程可能在 _at_cmd 等待回显期间把
                # 命令回应行读走，表现为「ATD 无响应」。
                with self._serial_lock:
                    if self._at_serial.in_waiting > 0:
                        raw = self._at_serial.readline()
                        line = raw.decode("ascii", errors="replace").strip() if raw else ""
                    else:
                        line = ""
                if line:
                    if _looks_like_urc(line):
                        self._handle_urc(line)
                    else:
                        # 不是 URC 就是命令回应，交给等待中的 _at_cmd
                        self._pending_urc.append(line)
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
