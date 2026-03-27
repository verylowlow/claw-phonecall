# AI Phone Agent - 配置模块
"""
项目配置管理
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# ADB 配置
ADB_CONFIG = {
    "timeout": 30,  # ADB 命令超时时间（秒）
    "poll_interval": 0.5,  # 通话状态轮询间隔（秒）
}

# 音频配置
AUDIO_CONFIG = {
    "sample_rate": 16000,  # 采样率（电话语音16kHz足够）
    "channels": 1,  # 单声道
    "format": "int16",  # 采样格式
    "buffer_size": 1024,  # 缓冲区大小
    "chunk_size": 4096,  # 音频块大小
}

# scrcpy 配置
SCRCPY_CONFIG = {
    "audio_codec": "opus",  # 音频编解码器
    "audio_bit_rate": 128000,
    "max_fps": 30,
}

# VAD 配置
VAD_CONFIG = {
    "threshold": 0.5,  # 语音检测阈值
    "min_speech_duration_ms": 250,  # 最小语音时长
    "min_silence_duration_ms": 300,  # 最小静音时长
    "speech_pad_ms": 400,  # 语音填充时长
}

# ASR 配置
ASR_CONFIG = {
    "model_size": "small",  # 模型大小 (tiny/small/medium/large)
    "device": "auto",  # 设备 (cpu/cuda/auto)
    "language": "zh",  # 语言
}

# TTS 配置
TTS_CONFIG = {
    "voice": "zh-CN-XiaoxiaoNeural",  # 默认音色
    "rate": "+0%",  # 语速
    "pitch": "+0Hz",  # 音调
    "volume": "+0%",  # 音量
}

# 拟人化配置
HUMANIZATION_CONFIG = {
    "filler_threshold_ms": 1200,  # 插入填充词的时间阈值
    "filler_phrases": ["嗯", "好的", "我在听", "明白"],  # 填充词列表
    "barge_in_enabled": True,  # 是否启用打断功能
}

# 通话控制配置
CALL_CONFIG = {
    "answer_delay": 2,  # 响铃后延迟接听时间（秒）
    "welcome_message": "喂，您好，请问哪位？",  # 欢迎语
    "max_call_duration": 1800,  # 最大通话时长（秒）
}

# 日志配置
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": PROJECT_ROOT / "logs" / "phone_agent.log",
}

# 多手机配置
MULTI_PHONE_CONFIG = {
    "max_concurrent_calls": 3,  # 最大并发通话数
    "process_isolation": True,  # 是否进程隔离
}