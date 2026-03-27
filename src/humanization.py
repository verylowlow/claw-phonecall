"""
AI Phone Agent - 拟人化策略模块
Humanization: 实现填充词、打断处理、静音检测等拟人化功能
"""

import threading
import time
import logging
import random
import numpy as np
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

from . import config

logger = logging.getLogger(__name__)


class HumanEventType(Enum):
    """拟人化事件类型"""
    SILENCE_DETECTED = "silence_detected"  # 检测到静音
    FILLER_PLAYED = "filler_played"  # 播放了填充词
    BARGE_IN_DETECTED = "barge_in_detected"  # 检测到打断
    SPEECH_DETECTED = "speech_detected"  # 检测到语音


@dataclass
class HumanEvent:
    """拟人化事件"""
    event_type: HumanEventType
    timestamp: float
    duration_ms: Optional[int] = None  # 静音时长或语音时长
    filler_phrase: Optional[str] = None  # 使用的填充词


class Humanization:
    """
    拟人化策略处理器
    处理填充词插入、打断检测等功能
    """
    
    def __init__(self):
        """初始化拟人化处理器"""
        # 配置参数
        self.filler_threshold_ms = config.HUMANIZATION_CONFIG["filler_threshold_ms"]
        self.filler_phrases: List[str] = config.HUMANIZATION_CONFIG["filler_phrases"]
        self.barge_in_enabled = config.HUMANIZATION_CONFIG["barge_in_enabled"]
        
        # 状态
        self._last_speech_time: float = 0
        self._last_response_time: float = 0
        self._silence_start_time: Optional[float] = None
        self._filler_played_recently = False
        self._lock = threading.Lock()
        
        # 回调
        self._callbacks: dict = {}
        
        logger.info("Humanization initialized")
    
    def on_speech_start(self) -> None:
        """检测到语音开始"""
        with self._lock:
            self._last_speech_time = time.time()
            self._silence_start_time = None
            self._filler_played_recently = False
            
            event = HumanEvent(
                event_type=HumanEventType.SPEECH_DETECTED,
                timestamp=self._last_speech_time
            )
            self._trigger_callback("on_speech", event)
        
        logger.debug("Speech detected")
    
    def on_speech_end(self, duration_ms: int) -> None:
        """
        检测到语音结束
        
        Args:
            duration_ms: 语音持续时长（毫秒）
        """
        with self._lock:
            self._silence_start_time = time.time()
            event = HumanEvent(
                event_type=HumanEventType.SILENCE_DETECTED,
                timestamp=self._silence_start_time,
                duration_ms=duration_ms
            )
            self._trigger_callback("on_silence", event)
        
        logger.debug(f"Speech ended, duration: {duration_ms}ms")
    
    def on_llm_response_start(self) -> None:
        """LLM 开始生成响应"""
        with self._lock:
            self._last_response_time = time.time()
            self._filler_played_recently = False
    
    def should_insert_filler(self) -> bool:
        """
        判断是否应该插入填充词
        
        Returns:
            bool: 是否应该插入
        """
        with self._lock:
            # 检查是否已经播放过填充词
            if self._filler_played_recently:
                return False
            
            # 检查是否在等待 LLM 响应
            if self._last_response_time == 0:
                return False
            
            # 检查静音时长
            if self._silence_start_time is None:
                return False
            
            silence_duration = (time.time() - self._silence_start_time) * 1000  # 转换为毫秒
            
            if silence_duration >= self.filler_threshold_ms:
                return True
            
            return False
    
    def get_filler(self) -> Optional[str]:
        """
        获取一个填充词
        
        Returns:
            str: 填充词，如果没有则返回 None
        """
        if not self.should_insert_filler():
            return None
        
        with self._lock:
            # 随机选择一个填充词
            filler = random.choice(self.filler_phrases)
            self._filler_played_recently = True
            
            event = HumanEvent(
                event_type=HumanEventType.FILLER_PLAYED,
                timestamp=time.time(),
                filler_phrase=filler
            )
            self._trigger_callback("on_filler", event)
            
            logger.info(f"Playing filler: {filler}")
            return filler
    
    def check_barge_in(self, audio_energy: float) -> bool:
        """
        检查是否检测到打断（用户开始说话）
        
        Args:
            audio_energy: 当前音频能量值 (0-1)
            
        Returns:
            bool: 是否检测到打断
        """
        if not self.barge_in_enabled:
            return False
        
        with self._lock:
            # 简单的能量阈值检测
            # 实际应用中应该结合 VAD 的结果
            barge_in_threshold = 0.3
            
            if audio_energy > barge_in_threshold:
                # 检测到可能的打断
                if self._silence_start_time is not None:
                    silence_duration = (time.time() - self._silence_start_time)
                    if silence_duration > 0.1:  # 至少 100ms 静音后才算打断
                        event = HumanEvent(
                            event_type=HumanEventType.BARGE_IN_DETECTED,
                            timestamp=time.time()
                        )
                        self._trigger_callback("on_barge_in", event)
                        logger.info("Barge-in detected")
                        return True
        
        return False
    
    def reset(self) -> None:
        """重置状态"""
        with self._lock:
            self._last_speech_time = 0
            self._last_response_time = 0
            self._silence_start_time = None
            self._filler_played_recently = False
        
        logger.info("Humanization state reset")
    
    def register_callback(self, event_type: str, callback: Callable) -> None:
        """
        注册回调函数
        
        Args:
            event_type: 事件类型 ("on_speech", "on_silence", "on_filler", "on_barge_in")
            callback: 回调函数
        """
        self._callbacks[event_type] = callback
    
    def _trigger_callback(self, event_type: str, event: HumanEvent) -> None:
        """触发回调"""
        if event_type in self._callbacks:
            try:
                self._callbacks[event_type](event)
            except Exception as e:
                logger.error(f"Error in callback {event_type}: {e}")


class FillerGenerator:
    """
    填充词生成器
    将文本填充词转换为音频数据
    """
    
    def __init__(self):
        """初始化填充词生成器"""
        self._audio_cache: dict = {}  # 缓存填充词音频
        
        logger.info("FillerGenerator initialized")
    
    def load_filler_audio(self, text: str, audio_data: bytes) -> None:
        """
        加载填充词音频数据
        
        Args:
            text: 填充词文本
            audio_data: PCM 音频数据
        """
        self._audio_cache[text] = audio_data
        logger.debug(f"Loaded filler audio for: {text}")
    
    def get_filler_audio(self, text: str) -> Optional[bytes]:
        """
        获取填充词音频
        
        Args:
            text: 填充词文本
            
        Returns:
            bytes: PCM 音频数据，如果没有则返回 None
        """
        return self._audio_cache.get(text)
    
    def has_filler_audio(self, text: str) -> bool:
        """检查是否有填充词音频"""
        return text in self._audio_cache


class BargeInHandler:
    """
    打断处理器
    处理用户打断 Agent 说话的场景
    """
    
    def __init__(self):
        """初始化打断处理器"""
        self.enabled = config.HUMANIZATION_CONFIG["barge_in_enabled"]
        self._is_speaking = False
        self._lock = threading.Lock()
        
        logger.info("BargeInHandler initialized")
    
    def start_speaking(self) -> None:
        """Agent 开始说话"""
        with self._lock:
            self._is_speaking = True
    
    def stop_speaking(self) -> None:
        """Agent 停止说话"""
        with self._lock:
            self._is_speaking = False
    
    def is_speaking(self) -> bool:
        """检查 Agent 是否正在说话"""
        with self._lock:
            return self._is_speaking
    
    def handle_barge_in(self) -> bool:
        """
        处理打断
        
        Returns:
            bool: 是否成功处理打断
        """
        if not self.enabled:
            return False
        
        with self._lock:
            if self._is_speaking:
                # Agent 正在说话时被用户打断
                self._is_speaking = False
                logger.info("Barge-in handled, stopping TTS")
                return True
        
        return False


def create_humanization() -> Humanization:
    """
    创建拟人化处理器
    
    Returns:
        Humanization 实例
    """
    return Humanization()