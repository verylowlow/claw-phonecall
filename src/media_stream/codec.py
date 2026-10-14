"""PCM (16-bit LE) and mu-law conversion for Twilio Media Streams (8 kHz)."""

from __future__ import annotations

try:
    import audioop
except ImportError:
    import audioop_lts as audioop  # Python 3.13+
import base64

_PCM_WIDTH = 2
_CHANNELS = 1


def pcm_to_mulaw(pcm_data: bytes, src_rate: int = 16000) -> bytes:
    """Convert PCM 16-bit signed little-endian to mu-law at 8 kHz."""
    fragment = pcm_data
    if src_rate != 8000:
        fragment, _ = audioop.ratecv(
            fragment, _PCM_WIDTH, _CHANNELS, src_rate, 8000, None
        )
    return audioop.lin2ulaw(fragment, _PCM_WIDTH)


def mulaw_to_pcm(mulaw_data: bytes, dst_rate: int = 16000) -> bytes:
    """Convert mu-law (8 kHz) to PCM 16-bit signed little-endian."""
    pcm = audioop.ulaw2lin(mulaw_data, _PCM_WIDTH)
    if dst_rate != 8000:
        pcm, _ = audioop.ratecv(pcm, _PCM_WIDTH, _CHANNELS, 8000, dst_rate, None)
    return pcm


def encode_payload(pcm_data: bytes, src_rate: int = 16000) -> str:
    """PCM -> mu-law @ 8 kHz -> base64 ASCII string."""
    mulaw = pcm_to_mulaw(pcm_data, src_rate=src_rate)
    return base64.b64encode(mulaw).decode("ascii")


def decode_payload(payload_b64: str, dst_rate: int = 16000) -> bytes:
    """Base64 -> mu-law -> PCM 16-bit LE (optionally resampled to dst_rate)."""
    mulaw = base64.b64decode(payload_b64, validate=True)
    return mulaw_to_pcm(mulaw, dst_rate=dst_rate)


def chunk_duration_samples(rate: int = 8000, duration_ms: int = 20) -> int:
    """Samples per chunk for a given sample rate and frame duration in ms."""
    return int(rate * duration_ms / 1000)
