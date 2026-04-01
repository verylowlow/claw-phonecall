"""Bidirectional call recorder — captures uplink and downlink PCM streams."""

from __future__ import annotations

import io
import logging
import struct
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 8000
_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit


class CallRecorder:
    """Records a single call's audio to WAV files."""

    def __init__(self, call_sid: str, phone_number: str, output_dir: Path):
        self._call_sid = call_sid
        safe_number = phone_number.replace("+", "").replace(" ", "_")
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        self._dir = output_dir / safe_number
        self._dir.mkdir(parents=True, exist_ok=True)
        self._prefix = f"{ts}_{call_sid[:10]}"

        self._uplink_buf = io.BytesIO()
        self._downlink_buf = io.BytesIO()
        self._lock = threading.Lock()
        self._recording = True

    def feed_uplink(self, pcm: bytes) -> None:
        if not self._recording:
            return
        with self._lock:
            self._uplink_buf.write(pcm)

    def feed_downlink(self, pcm: bytes) -> None:
        if not self._recording:
            return
        with self._lock:
            self._downlink_buf.write(pcm)

    def stop(self) -> Optional[str]:
        """Stop recording and save WAV files. Returns the mixed file path."""
        self._recording = False
        with self._lock:
            uplink = self._uplink_buf.getvalue()
            downlink = self._downlink_buf.getvalue()

        if not uplink and not downlink:
            logger.info("No audio recorded for call %s", self._call_sid)
            return None

        mixed_path = self._dir / f"{self._prefix}_mixed.wav"
        mixed = self._mix_audio(uplink, downlink)
        _write_wav(mixed_path, mixed)

        if uplink:
            _write_wav(self._dir / f"{self._prefix}_uplink.wav", uplink)
        if downlink:
            _write_wav(self._dir / f"{self._prefix}_downlink.wav", downlink)

        logger.info("Saved recording for call %s: %s", self._call_sid, mixed_path)
        return str(mixed_path)

    @staticmethod
    def _mix_audio(uplink: bytes, downlink: bytes) -> bytes:
        """Mix two PCM streams by averaging samples."""
        max_len = max(len(uplink), len(downlink))
        if max_len == 0:
            return b""

        up = uplink.ljust(max_len, b"\x00")
        down = downlink.ljust(max_len, b"\x00")

        num_samples = max_len // 2
        fmt = f"<{num_samples}h"
        up_samples = struct.unpack(fmt, up[:num_samples * 2])
        down_samples = struct.unpack(fmt, down[:num_samples * 2])

        mixed = struct.pack(
            fmt,
            *(max(-32768, min(32767, (a + b) // 2))
              for a, b in zip(up_samples, down_samples))
        )
        return mixed


def _write_wav(path: Path, pcm: bytes) -> None:
    """Write raw PCM data as a WAV file."""
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,                    # PCM format
        _CHANNELS,
        _SAMPLE_RATE,
        _SAMPLE_RATE * _CHANNELS * _SAMPLE_WIDTH,
        _CHANNELS * _SAMPLE_WIDTH,
        _SAMPLE_WIDTH * 8,
        b"data",
        data_size,
    )
    path.write_bytes(header + pcm)
