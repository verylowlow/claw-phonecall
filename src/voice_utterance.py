"""
句末分句（对齐 Voice-call：仅在停顿足够长后提交整段 PCM 给 ASR）。
结合能量门限与可选 VAD 结果；支持检测「用户开始说话」用于打断（barge-in）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class UtteranceSegmenterConfig:
    sample_rate: int = 16000
    channels: int = 1
    bytes_per_sample: int = 2
    # 句末静音长度（与 voice-call OpenAI server_vad silence_duration_ms 同量级）
    end_silence_ms: float = 750.0
    # 视为一句话所需的最短语音时长
    min_speech_ms: float = 250.0
    # 能量门限：高于则认为有语音（与 VAD 结果取或）
    energy_speech: float = 0.035
    # 低于则认为静音（略低于 energy_speech，形成滞回）
    energy_silence: float = 0.022
    max_utterance_ms: float = 15000.0


@dataclass
class UtteranceSegmenter:
    """
    逐块喂入 PCM，返回：
    - speech_just_started: 本块是否为用户从静音切入说话（用于 barge-in）
    - finalized: 若本块结束时凑齐一句，返回整段 PCM（否则 None）
    """

    cfg: UtteranceSegmenterConfig = field(default_factory=UtteranceSegmenterConfig)
    _buf: bytearray = field(default_factory=bytearray, init=False)
    _silence_ms: float = field(default=0.0, init=False)
    _speech_ms: float = field(default=0.0, init=False)
    _had_speech: bool = field(default=False, init=False)
    _prev_is_speech: bool = field(default=False, init=False)
    _utterance_speech_ms: float = field(default=0.0, init=False)

    def reset(self) -> None:
        self._buf.clear()
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._had_speech = False
        self._prev_is_speech = False
        self._utterance_speech_ms = 0.0

    def _chunk_duration_ms(self, pcm: bytes) -> float:
        bps = self.cfg.channels * self.cfg.bytes_per_sample
        if bps <= 0:
            return 0.0
        return (len(pcm) / bps) / self.cfg.sample_rate * 1000.0

    @staticmethod
    def _rms_energy(pcm: bytes) -> float:
        if not pcm or len(pcm) < 2:
            return 0.0
        audio = np.frombuffer(pcm, dtype=np.int16)
        if audio.size == 0:
            return 0.0
        return float(np.abs(audio).mean() / 32768.0)

    def _is_speech_chunk(self, pcm: bytes, vad_is_speech: bool) -> bool:
        e = self._rms_energy(pcm)
        if vad_is_speech:
            return True
        if self._prev_is_speech:
            return e >= self.cfg.energy_silence
        return e >= self.cfg.energy_speech

    def feed(self, pcm: bytes, vad_is_speech: bool) -> Tuple[Optional[bytes], bool]:
        """
        Returns:
            (finalized_utterance_pcm_or_none, speech_just_started)
        """
        if not pcm:
            return None, False

        dt = self._chunk_duration_ms(pcm)
        is_speech = self._is_speech_chunk(pcm, vad_is_speech)
        speech_just_started = is_speech and not self._prev_is_speech
        self._prev_is_speech = is_speech

        finalized: Optional[bytes] = None

        if is_speech:
            self._silence_ms = 0.0
            self._speech_ms += dt
            self._buf.extend(pcm)
            if self._speech_ms >= self.cfg.min_speech_ms:
                self._had_speech = True
            if self._had_speech:
                self._utterance_speech_ms += dt
        else:
            self._speech_ms = 0.0
            if self._had_speech:
                self._buf.extend(pcm)
                self._silence_ms += dt
                max_ms = self.cfg.max_utterance_ms
                utter_ms = (len(self._buf) / (self.cfg.channels * self.cfg.bytes_per_sample)) / self.cfg.sample_rate * 1000.0
                if self._silence_ms >= self.cfg.end_silence_ms or utter_ms >= max_ms:
                    finalized = bytes(self._buf)
                    self.reset()
                    return finalized, speech_just_started
            else:
                self._buf.clear()
                self._utterance_speech_ms = 0.0

        return None, speech_just_started
