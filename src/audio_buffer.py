"""
Audio Buffer - 语音段累积模块
累积完整语音段，等待 VAD 检测到静音段后送 ASR
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AudioBuffer:
    """
    音频缓冲区
    累积完整语音段，等待 VAD 检测到静音段后送 ASR
    """

    def __init__(self, max_duration_ms: int = 10000, sample_rate: int = 16000, channels: int = 1):
        """
        初始化音频缓冲区

        Args:
            max_duration_ms: 最大累积时长（毫秒）
            sample_rate: 采样率
            channels: 声道数
        """
        self._buffer = io.BytesIO()
        self._max_duration_ms = max_duration_ms
        self._sample_rate = sample_rate
        self._channels = channels
        self._bytes_per_sample = 2  # 16bit PCM
        self._max_bytes = (max_duration_ms // 1000) * sample_rate * channels * self._bytes_per_sample
        self._current_bytes = 0

    def add(self, audio_chunk: bytes) -> None:
        """
        添加音频数据

        Args:
            audio_chunk: PCM 音频数据
        """
        chunk_size = len(audio_chunk)

        # 超过最大容量时，移除旧数据
        if self._current_bytes + chunk_size > self._max_bytes:
            excess = (self._current_bytes + chunk_size) - self._max_bytes
            # 移动缓冲区起点
            self._buffer.seek(excess)
            remaining = self._buffer.read()
            self._buffer = io.BytesIO()
            self._buffer.write(remaining)
            self._current_bytes = len(remaining)

        self._buffer.write(audio_chunk)
        self._current_bytes += chunk_size

    def is_complete(self, vad_result) -> bool:
        """
        判断是否累积完成（检测到静音段）

        Args:
            vad_result: VAD 检测结果

        Returns:
            bool: 是否累积完成
        """
        if vad_result is None:
            return False

        # 检查是否有静音段（表示用户一句话结束）
        return getattr(vad_result, 'has_silence_after_speech', False)

    def get_audio(self) -> bytes:
        """
        获取累积的音频数据

        Returns:
            bytes: 累积的音频数据
        """
        self._buffer.seek(0)
        return self._buffer.read()

    def clear(self) -> None:
        """清空缓冲区"""
        self._buffer = io.BytesIO()
        self._current_bytes = 0

    def has_content(self) -> bool:
        """
        检查缓冲区是否有内容

        Returns:
            bool: 是否有音频数据
        """
        return self._current_bytes > 0

    @property
    def duration_ms(self) -> int:
        """
        当前缓冲区时长（毫秒）

        Returns:
            int: 时长
        """
        return (self._current_bytes // (self._sample_rate * self._channels * self._bytes_per_sample)) * 1000