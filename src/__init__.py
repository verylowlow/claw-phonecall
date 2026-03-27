"""
AI Phone Agent - 核心模块
"""

__version__ = "1.0.0"
__author__ = "AI Phone Agent Team"

from .phone_controller import PhoneController, CallState, PhoneEvent
from .audio_capture import AudioCapture, AudioCaptureError
from .audio_player import AudioPlayer, AudioPlayerError
from .humanization import Humanization, HumanEvent, HumanEventType
from .ai_pipeline import AIPipeline, PipelineState, Transcript, PipelineEvent
from . import config

__all__ = [
    # 版本
    "__version__",
    # 配置
    "config",
    # 手机控制
    "PhoneController",
    "CallState", 
    "PhoneEvent",
    # 音频捕获
    "AudioCapture",
    "AudioCaptureError",
    # 音频播放
    "AudioPlayer",
    "AudioPlayerError",
    # 拟人化
    "Humanization",
    "HumanEvent",
    "HumanEventType",
    # AI 管道
    "AIPipeline",
    "PipelineState",
    "Transcript",
    "PipelineEvent",
]