"""Twilio Media Stream WebSocket protocol messages."""

from __future__ import annotations

import json
from typing import Any, Optional


def build_start_message(
    stream_sid: str,
    call_sid: str,
    account_sid: str,
    token: Optional[str] = None,
) -> str:
    custom_params: dict[str, str] = {}
    if token:
        custom_params["token"] = token
    msg: dict[str, Any] = {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": stream_sid,
        "start": {
            "streamSid": stream_sid,
            "accountSid": account_sid,
            "callSid": call_sid,
            "tracks": ["inbound"],
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "channels": 1,
            },
            "customParameters": custom_params,
        },
    }
    return json.dumps(msg, separators=(",", ":"))


def build_media_message(
    stream_sid: str,
    payload_b64: str,
    seq_num: int,
    chunk_num: int,
    timestamp_ms: int,
    track: str = "inbound",
) -> str:
    msg: dict[str, Any] = {
        "event": "media",
        "sequenceNumber": str(seq_num),
        "streamSid": stream_sid,
        "media": {
            "track": track,
            "chunk": str(chunk_num),
            "timestamp": str(timestamp_ms),
            "payload": payload_b64,
        },
    }
    return json.dumps(msg, separators=(",", ":"))


def build_stop_message(stream_sid: str) -> str:
    return json.dumps(
        {"event": "stop", "streamSid": stream_sid},
        separators=(",", ":"),
    )


def build_clear_message(stream_sid: str) -> str:
    return json.dumps(
        {"event": "clear", "streamSid": stream_sid},
        separators=(",", ":"),
    )


def build_mark_message(stream_sid: str, name: str) -> str:
    return json.dumps(
        {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}},
        separators=(",", ":"),
    )


def parse_message(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"event": "unknown", "raw": data}
    return data
