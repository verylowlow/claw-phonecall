"""Tests for the call recorder."""

import struct
import tempfile
from pathlib import Path

from src.recording.recorder import CallRecorder


def test_recorder_basic(tmp_path):
    rec = CallRecorder("CA_test_123", "+8613800001111", tmp_path)

    pcm_100hz = struct.pack("<160h", *([1000] * 80 + [-1000] * 80))
    rec.feed_uplink(pcm_100hz)
    rec.feed_downlink(pcm_100hz)

    path = rec.stop()
    assert path is not None
    assert Path(path).exists()
    assert path.endswith("_mixed.wav")

    phone_dir = tmp_path / "8613800001111"
    assert phone_dir.exists()
    wav_files = list(phone_dir.glob("*.wav"))
    assert len(wav_files) == 3  # mixed, uplink, downlink


def test_recorder_empty(tmp_path):
    rec = CallRecorder("CA_empty", "+8600000000", tmp_path)
    path = rec.stop()
    assert path is None


def test_recorder_uplink_only(tmp_path):
    rec = CallRecorder("CA_up", "+8611111111", tmp_path)
    rec.feed_uplink(b"\x00\x01" * 100)
    path = rec.stop()
    assert path is not None
    wav_files = list((tmp_path / "8611111111").glob("*.wav"))
    assert len(wav_files) == 2  # mixed + uplink
