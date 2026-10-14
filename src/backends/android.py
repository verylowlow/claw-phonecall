"""
Android backend — control an Android phone via ADB + capture audio via scrcpy.

Reuses the patterns from the original agentcalls project but adapted to the
TelephonyBackend interface for use with the AgentCallCenter bridge.

Hardware chain: Android phone (USB) -> ADB (control) + scrcpy (audio capture)
               PC sound card -> audio cable -> phone 3.5mm jack (downlink)
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import subprocess
import threading
import time
from typing import Optional

from .base import TelephonyBackend, CallState

logger = logging.getLogger(__name__)


class AndroidBackend(TelephonyBackend):
    """Telephony backend using ADB + scrcpy for Android phones."""

    def __init__(self, device_id: Optional[str] = None):
        self._device_id = device_id
        self._state = CallState.IDLE
        self._healthy = False
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._capture_running = threading.Event()
        self._rx_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self._tx_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)

    async def initialize(self) -> None:
        result = await asyncio.to_thread(
            subprocess.run,
            ["adb", "devices"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"adb not available: {result.stderr}")

        lines = result.stdout.strip().split("\n")
        devices = [l.split("\t")[0] for l in lines[1:] if "\tdevice" in l]
        if not devices:
            raise RuntimeError("No Android devices connected")

        if self._device_id and self._device_id not in devices:
            raise RuntimeError(f"Device {self._device_id} not found. Available: {devices}")

        if not self._device_id:
            self._device_id = devices[0]

        self._healthy = True
        logger.info("Android backend initialized: device=%s", self._device_id)

    async def dial(self, number: str) -> bool:
        number = number.strip().replace(" ", "").replace("-", "")
        cmd = self._adb_cmd(f"am start -a android.intent.action.CALL tel:{number}")
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            logger.error("Dial failed: %s", result.stderr)
            return False

        self._state = CallState.DIALING
        logger.info("Dialing %s on Android...", number)

        for _ in range(60):
            await asyncio.sleep(1)
            state = await self._poll_call_state()
            if state == CallState.ACTIVE:
                self._state = CallState.ACTIVE
                self._start_audio_capture()
                return True
            if state == CallState.IDLE:
                self._state = CallState.IDLE
                return False

        self._state = CallState.IDLE
        return False

    async def answer(self) -> bool:
        cmd = self._adb_cmd("input keyevent 5")
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            self._state = CallState.ACTIVE
            self._start_audio_capture()
            return True
        return False

    async def hangup(self) -> bool:
        self._stop_audio_capture()
        cmd = self._adb_cmd("input keyevent 6")
        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=5
        )
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
        return self._healthy

    async def shutdown(self) -> None:
        self._stop_audio_capture()
        if self._state != CallState.IDLE:
            await self.hangup()
        self._healthy = False

    def device_info(self) -> dict:
        return {
            "type": "AndroidBackend",
            "device_id": self._device_id,
            "healthy": self._healthy,
            "state": self._state.name,
        }

    def _adb_cmd(self, shell_cmd: str) -> list:
        cmd = ["adb"]
        if self._device_id:
            cmd.extend(["-s", self._device_id])
        cmd.extend(["shell", shell_cmd])
        return cmd

    async def _poll_call_state(self) -> CallState:
        cmd = self._adb_cmd("dumpsys telephony.registry | grep mCallState")
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return CallState.IDLE
        try:
            for line in result.stdout.split("\n"):
                if "mCallState" in line:
                    val = int(line.split("=")[1].strip())
                    if val == 0:
                        return CallState.IDLE
                    elif val == 1:
                        return CallState.RINGING
                    elif val == 2:
                        return CallState.ACTIVE
        except (IndexError, ValueError):
            pass
        return CallState.IDLE

    def _start_audio_capture(self) -> None:
        if self._capture_running.is_set():
            return

        scrcpy_cmd = ["scrcpy", "--no-video", "--no-control",
                       "--audio-source", "voice-performance",
                       "--audio-codec", "opus",
                       "--record-format", "mkv",
                       "--record", "-"]
        if self._device_id:
            scrcpy_cmd.extend(["-s", self._device_id])

        ffmpeg_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
                      "-f", "matroska", "-i", "pipe:0",
                      "-ar", "8000", "-ac", "1",
                      "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]

        kw = {}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self._scrcpy_proc = subprocess.Popen(
            scrcpy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw
        )
        self._ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=self._scrcpy_proc.stdout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw
        )
        if self._scrcpy_proc.stdout:
            self._scrcpy_proc.stdout.close()

        self._capture_running.set()
        threading.Thread(target=self._capture_loop, daemon=True).start()
        logger.info("Android audio capture started")

    def _stop_audio_capture(self) -> None:
        self._capture_running.clear()
        for proc in (self._ffmpeg_proc, self._scrcpy_proc):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._ffmpeg_proc = None
        self._scrcpy_proc = None

    def _capture_loop(self) -> None:
        while self._capture_running.is_set():
            if not self._ffmpeg_proc or not self._ffmpeg_proc.stdout:
                break
            try:
                data = self._ffmpeg_proc.stdout.read(320)  # 20ms at 8kHz 16-bit mono
                if data:
                    try:
                        self._rx_queue.put_nowait(data)
                    except queue.Full:
                        pass
                else:
                    time.sleep(0.01)
            except Exception:
                break
