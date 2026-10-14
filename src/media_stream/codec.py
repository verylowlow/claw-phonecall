"""PCM (16-bit LE) and mu-law conversion for Twilio Media Streams (8 kHz).

Twilio Media Streams 用 8 kHz mu-law 承载音频。标准库 audioop 在 Python 3.13
被移除，而第三方回退包 audioop-lts 在很多环境里装不上（离线 / 内网 / 无预编译轮子），
一旦导入失败，整条媒体链路在启动时就抛 ModuleNotFoundError。

所以这里自带一份纯 Python 实现作为兜底：只依赖标准库，慢一些但零依赖，
嵌入式设备与离线环境下也能跑。装了 audioop 时仍然优先用它（快1~2 个数量级）。
"""

from __future__ import annotations

import base64

_PCM_WIDTH = 2
_CHANNELS = 1

# ── audioop 可选加速 ──
try:  # Python <= 3.12 标准库自带
    import audioop as _audioop
except ImportError:  # pragma: no cover - 取决于运行环境
    try:  # Python 3.13+ 且装了回退包
        import audioop_lts as _audioop  # type: ignore[no-redef]
    except ImportError:  # 纯 Python 兜底
        _audioop = None  # type: ignore[assignment]

# ── 纯 Python mu-law（G.711）编解码 ──
# 常量取自 ITU-T G.711 参考实现：输入先算术右移 2 位压到 14 bit，
# 段边界表随之也是 14 bit 量级（0x3F…0x1FFF），不是 16 bit 的0xFF…0x7FFF。
_BIAS = 0x84
_CLIP = 8159
_SEG_END = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)


def _linear_to_mulaw(sample: int) -> int:
    """16-bit 线性 PCM 单样本 -> 1 字节 mu-law。"""
    sample >>= 2  # 16 bit -> 14 bit，算术右移保留符号
    if sample < 0:
        sample = -sample
        mask = 0x7F
    else:
        mask = 0xFF

    if sample > _CLIP:
        sample = _CLIP
    sample += _BIAS >> 2

    seg = 8
    for i, end in enumerate(_SEG_END):
        if sample <= end:
            seg = i
            break

    if seg >= 8:
        return 0x7F ^ mask

    uval = (seg << 4) | ((sample >> (seg + 1)) & 0x0F)
    return uval ^ mask


def _mulaw_to_linear(u: int) -> int:
    """1 字节 mu-law -> 16-bit 线性 PCM。满量程解码值 32124。"""
    u = ~u & 0xFF
    t = ((u & 0x0F) << 3) + _BIAS
    t <<= (u & 0x70) >> 4
    return (_BIAS - t) if (u & 0x80) else (t - _BIAS)


def _unpack_pcm(pcm_data: bytes) -> list[int]:
    n = len(pcm_data) - (len(pcm_data) % _PCM_WIDTH)
    return [
        pcm_data[i] | (pcm_data[i + 1] << 8)
        if pcm_data[i + 1] < 0x80
        else (pcm_data[i] | (pcm_data[i + 1] << 8)) - 0x10000
        for i in range(0, n, 2)
    ]


def _pack_pcm(samples: list[int]) -> bytes:
    out = bytearray(len(samples) * 2)
    for i, s in enumerate(samples):
        s = max(-32768, min(32767, int(s)))
        out[i * 2] = s & 0xFF
        out[i * 2 + 1] = (s >> 8) & 0xFF
    return bytes(out)


def _pcm_to_mulaw_py(pcm_data: bytes) -> bytes:
    return bytes(u & 0xFF for u in map(_linear_to_mulaw, _unpack_pcm(pcm_data)))


def _mulaw_to_pcm_py(mulaw_data: bytes) -> bytes:
    return _pack_pcm([_mulaw_to_linear(b) for b in mulaw_data])


def _ratecv_py(pcm_data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """线性插值重采样。仅在 audioop 不可用时使用。"""
    if src_rate == dst_rate:
        return pcm_data
    samples = _unpack_pcm(pcm_data)
    n = len(samples)
    if n == 0:
        return b""
    ratio = src_rate / dst_rate
    out_len = max(1, int(n / ratio))
    out: list[int] = []
    for i in range(out_len):
        pos = i * ratio
        i0 = int(pos)
        i1 = min(i0 + 1, n - 1)
        frac = pos - i0
        out.append(samples[i0] * (1 - frac) + samples[i1] * frac)
    return _pack_pcm(out)


def pcm_to_mulaw(pcm_data: bytes, src_rate: int = 16000) -> bytes:
    """Convert PCM 16-bit signed little-endian to mu-law at 8 kHz."""
    fragment = pcm_data
    if src_rate != 8000:
        if _audioop is not None:
            fragment, _ = _audioop.ratecv(
                fragment, _PCM_WIDTH, _CHANNELS, src_rate, 8000, None
            )
        else:
            fragment = _ratecv_py(fragment, src_rate, 8000)
    if _audioop is not None:
        return _audioop.lin2ulaw(fragment, _PCM_WIDTH)
    return _pcm_to_mulaw_py(fragment)


def mulaw_to_pcm(mulaw_data: bytes, dst_rate: int = 16000) -> bytes:
    """Convert mu-law (8 kHz) to PCM 16-bit signed little-endian."""
    if _audioop is not None:
        pcm = _audioop.ulaw2lin(mulaw_data, _PCM_WIDTH)
    else:
        pcm = _mulaw_to_pcm_py(mulaw_data)
    if dst_rate != 8000:
        if _audioop is not None:
            pcm, _ = _audioop.ratecv(pcm, _PCM_WIDTH, _CHANNELS, 8000, dst_rate, None)
        else:
            pcm = _ratecv_py(pcm, 8000, dst_rate)
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