"""AgentCallCenter: Twilio-compatible local telephony bridge — configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final, TypedDict

from dotenv import load_dotenv

load_dotenv()

_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT: Final[Path] = _THIS_FILE.parent.parent


def _env_str(key: str, default: str) -> str:
    v = os.getenv(key)
    return default if v is None or v.strip() == "" else v


class BridgeConfigDict(TypedDict):
    host: str
    port: int
    web_port: int
    backend_type: str
    voice_call_stream_url: str
    voice_call_webhook_url: str


class TwilioCompatConfigDict(TypedDict):
    account_sid: str
    auth_token: str


class AudioConfigDict(TypedDict):
    sample_rate: int
    channels: int
    format: str
    chunk_duration_ms: int


class RecordingConfigDict(TypedDict):
    enabled: bool
    directory: Path
    retain_days: int
    format: str


class DbConfigDict(TypedDict):
    path: Path


class LogConfigDict(TypedDict):
    level: str
    format: str
    path: Path


BRIDGE_CONFIG: BridgeConfigDict = {
    "host": "0.0.0.0",
    "port": 8080,
    "web_port": 8090,
    "backend_type": _env_str("BRIDGE_BACKEND", "mock"),
    "voice_call_stream_url": _env_str(
        "VOICE_CALL_STREAM_URL",
        "ws://127.0.0.1:3334/voice/stream",
    ),
    "voice_call_webhook_url": _env_str(
        "VOICE_CALL_WEBHOOK_URL",
        "http://127.0.0.1:3334/voice/webhook",
    ),
}

TWILIO_COMPAT_CONFIG: TwilioCompatConfigDict = {
    "account_sid": _env_str("TWILIO_ACCOUNT_SID", "LOCAL_BRIDGE"),
    "auth_token": _env_str("TWILIO_AUTH_TOKEN", "local_token"),
}

AUDIO_CONFIG: AudioConfigDict = {
    "sample_rate": 8000,
    "channels": 1,
    "format": "mulaw",
    "chunk_duration_ms": 20,
}

RECORDING_CONFIG: RecordingConfigDict = {
    "enabled": True,
    "directory": PROJECT_ROOT / "recordings",
    "retain_days": 30,
    "format": "wav",
}

DB_CONFIG: DbConfigDict = {
    "path": PROJECT_ROOT / "data" / "agentcallcenter.db",
}

_DEFAULT_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

LOG_CONFIG: LogConfigDict = {
    "level": "INFO",
    "format": _DEFAULT_LOG_FORMAT,
    "path": PROJECT_ROOT / "logs" / "agentcallcenter.log",
}


def configure_logging(
    *,
    level: str | None = None,
    log_format: str | None = None,
    log_path: Path | str | None = None,
) -> None:
    """Configure root logger: file + stderr, idempotent if handlers already exist."""
    lvl = (level or LOG_CONFIG["level"]).upper()
    fmt = log_format or LOG_CONFIG["format"]
    path = Path(log_path) if log_path is not None else LOG_CONFIG["path"]

    numeric = getattr(logging, lvl, logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)

    if root.handlers:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(fmt)

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(numeric)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric)
    stream_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)
