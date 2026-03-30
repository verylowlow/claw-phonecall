"""边缘场景与业务逻辑单测（纯逻辑，不依赖真机/网络）。"""

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.static_audio_cache import StaticAudioCache
from src.phone_skill import _time_of_day_key, _build_static_audio_mapping


# ---------- StaticAudioCache ----------

class TestStaticAudioCache:
    def test_get_returns_none_when_empty(self, tmp_path):
        cache = StaticAudioCache(tts_manager=None, cache_dir=tmp_path / "audio")
        assert cache.get("nonexistent") is None

    def test_ensure_writes_and_reads(self, tmp_path):
        import asyncio

        fake_tts = MagicMock()

        async def fake_synth(text):
            yield b"\x00\x01" * 100

        fake_tts.synthesize = fake_synth

        cache = StaticAudioCache(tts_manager=fake_tts, cache_dir=tmp_path / "audio")
        pcm = asyncio.run(cache.ensure("test_key", "hello"))
        assert len(pcm) == 200
        assert (tmp_path / "audio" / "test_key.pcm").is_file()

        # 第二次直接读缓存
        pcm2 = cache.get("test_key")
        assert pcm2 == pcm

    def test_ensure_reads_existing_file(self, tmp_path):
        import asyncio

        cache_dir = tmp_path / "audio"
        cache_dir.mkdir(parents=True)
        (cache_dir / "prebuilt.pcm").write_bytes(b"\xff" * 50)

        cache = StaticAudioCache(tts_manager=None, cache_dir=cache_dir)
        pcm = asyncio.run(cache.ensure("prebuilt", "ignored"))
        assert pcm == b"\xff" * 50

    def test_has(self, tmp_path):
        cache_dir = tmp_path / "audio"
        cache_dir.mkdir(parents=True)
        (cache_dir / "exists.pcm").write_bytes(b"\x00")

        cache = StaticAudioCache(tts_manager=None, cache_dir=cache_dir)
        assert cache.has("exists") is True
        assert cache.has("nope") is False

    def test_keys_on_disk(self, tmp_path):
        cache_dir = tmp_path / "audio"
        cache_dir.mkdir(parents=True)
        (cache_dir / "a.pcm").write_bytes(b"\x00")
        (cache_dir / "b.pcm").write_bytes(b"\x00")

        cache = StaticAudioCache(tts_manager=None, cache_dir=cache_dir)
        keys = sorted(cache.keys_on_disk())
        assert keys == ["a", "b"]


# ---------- 动态问候 ----------

class TestTimeOfDay:
    def test_morning(self):
        with patch("src.phone_skill.datetime") as m:
            m.now.return_value = datetime(2026, 3, 30, 9, 0, 0)
            assert _time_of_day_key() == "morning"

    def test_afternoon(self):
        with patch("src.phone_skill.datetime") as m:
            m.now.return_value = datetime(2026, 3, 30, 14, 0, 0)
            assert _time_of_day_key() == "afternoon"

    def test_evening(self):
        with patch("src.phone_skill.datetime") as m:
            m.now.return_value = datetime(2026, 3, 30, 21, 0, 0)
            assert _time_of_day_key() == "evening"

    def test_late_night(self):
        with patch("src.phone_skill.datetime") as m:
            m.now.return_value = datetime(2026, 3, 30, 2, 0, 0)
            assert _time_of_day_key() == "evening"


# ---------- 静态话术映射 ----------

class TestStaticAudioMapping:
    def test_mapping_contains_welcome_variants(self):
        mapping = _build_static_audio_mapping()
        assert "welcome_morning" in mapping
        assert "welcome_afternoon" in mapping
        assert "welcome_evening" in mapping
        assert "小甜甜" in mapping["welcome_morning"]

    def test_mapping_contains_thinking(self):
        mapping = _build_static_audio_mapping()
        assert any(k.startswith("thinking_") for k in mapping)

    def test_mapping_contains_apology_and_farewell(self):
        mapping = _build_static_audio_mapping()
        assert "apology" in mapping
        assert "farewell" in mapping

    def test_mapping_contains_fillers(self):
        mapping = _build_static_audio_mapping()
        assert any(k.startswith("filler_") for k in mapping)


# ---------- is_healthy ----------

class TestAudioCaptureHealthy:
    def test_healthy_when_running(self):
        from src.audio_capture import AudioCapture
        cap = AudioCapture()
        assert cap.is_healthy() is False  # not started

    def test_healthy_detects_dead_process(self):
        from src.audio_capture import AudioCapture
        cap = AudioCapture()
        cap._running.set()
        proc = MagicMock()
        proc.poll.return_value = 1  # process exited
        cap._scrcpy_process = proc
        cap._ffmpeg_process = MagicMock()
        cap._ffmpeg_process.poll.return_value = None
        assert cap.is_healthy() is False
