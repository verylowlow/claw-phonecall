"""配置与工具路径解析（无需真机）。"""

import pytest

from src import config
from src.audio_capture import AudioCapture


def test_get_tool_path_ffmpeg_default():
    assert config.get_tool_path("ffmpeg") == "ffmpeg"


def test_get_tool_path_adb_default():
    assert config.get_tool_path("adb") == "adb"


def test_volc_asr_configured_returns_bool():
    assert isinstance(config.volc_asr_configured(), bool)


def test_scrcpy_cmd_contains_expected_flags(monkeypatch):
    monkeypatch.setenv("AGENTCALLS_SCRCPY", "fake-scrcpy")
    cap = AudioCapture()
    cmd = cap._build_scrcpy_command()
    assert cmd[0] == "fake-scrcpy"
    joined = " ".join(cmd)
    assert "--no-video" in joined
    assert "--record" in joined
    assert "-" in cmd


def test_ffmpeg_cmd_uses_tool_path(monkeypatch):
    monkeypatch.setenv("AGENTCALLS_FFMPEG", "my-ffmpeg")
    cap = AudioCapture()
    cmd = cap._build_ffmpeg_command()
    assert cmd[0] == "my-ffmpeg"
    assert "pipe:0" in cmd


def test_default_scrcpy_inside_project(tmp_path, monkeypatch):
    """若存在 vendor 目录则自动选用。"""
    fake_root = tmp_path / "proj"
    (fake_root / "scrcpy-win64-v3.3.3").mkdir(parents=True)
    exe = fake_root / "scrcpy-win64-v3.3.3" / "scrcpy.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(config, "PROJECT_ROOT", fake_root)
    monkeypatch.delenv("AGENTCALLS_SCRCPY", raising=False)
    assert config._default_scrcpy_path() == str(exe)
