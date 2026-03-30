"""UtteranceSegmenter：句末分句与 speech_just_started（barge-in 信号）。"""

import numpy as np

from src.voice_utterance import UtteranceSegmenter, UtteranceSegmenterConfig


def _pcm_silence(ms: int, sr: int = 16000) -> bytes:
    n = int(sr * ms / 1000) * 2
    return bytes(n)


def _pcm_tone(ms: int, sr: int = 16000, amp: int = 8000) -> bytes:
    n = int(sr * ms / 1000)
    t = np.linspace(0, 2 * np.pi * 440 * ms / 1000, n, endpoint=False)
    samples = (amp * np.sin(t)).astype(np.int16)
    return samples.tobytes()


def test_speech_just_started_on_transition():
    cfg = UtteranceSegmenterConfig(
        end_silence_ms=200.0,
        min_speech_ms=50.0,
        energy_speech=0.01,
        energy_silence=0.008,
    )
    seg = UtteranceSegmenter(cfg)
    sil = _pcm_silence(50)
    sp = _pcm_tone(80)
    _f, started = seg.feed(sil, vad_is_speech=False)
    assert started is False
    _f, started = seg.feed(sp, vad_is_speech=True)
    assert started is True


def test_finalizes_after_end_silence():
    cfg = UtteranceSegmenterConfig(
        end_silence_ms=100.0,
        min_speech_ms=40.0,
        energy_speech=0.01,
        energy_silence=0.008,
    )
    seg = UtteranceSegmenter(cfg)
    sp = _pcm_tone(120)
    sil = _pcm_silence(150)
    seg.feed(sp, True)
    finalized, _ = seg.feed(sil, False)
    assert finalized is not None
    assert len(finalized) > 0
