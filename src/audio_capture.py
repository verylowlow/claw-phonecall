"""
AI Phone Agent - 音频捕获模块
AudioCapture: 通过 scrcpy 捕获安卓手机音频流
"""

import subprocess
import threading
import queue
import logging
import io
import struct
from typing import Optional, Generator
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


class AudioCaptureError(Exception):
    """音频捕获异常"""
    pass


class AudioCapture:
    """
    音频捕获器
    使用 scrcpy 捕获手机音频流
    """
    
    def __init__(self, device_id: Optional[str] = None):
        """
        初始化音频捕获器
        
        Args:
            device_id: 安卓设备 ID，用于多手机控制
        """
        self.device_id = device_id
        self._scrcpy_process: Optional[subprocess.Popen] = None
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._running = threading.Event()
        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        
        # 从配置获取参数
        self.sample_rate = config.AUDIO_CONFIG["sample_rate"]
        self.channels = config.AUDIO_CONFIG["channels"]
        
        logger.info(f"AudioCapture initialized for device: {device_id or 'default'}")
    
    def _build_scrcpy_command(self) -> list:
        """构建 scrcpy 命令"""
        cmd = ["scrcpy", "--no-video", "--no-control"]
        
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        
        # 音频配置
        cmd.extend([
            "--audio-codec", config.SCRCPY_CONFIG["audio_codec"],
            "--audio-bit-rate", str(config.SCRCPY_CONFIG["audio_bit_rate"]),
        ])
        
        return cmd
    
    def _build_ffmpeg_command(self) -> list:
        """构建 ffmpeg 命令用于重采样"""
        # 从 opus 转码为 16kHz PCM
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "opus",  # 输入格式
            "-i", "pipe:0",  # 从 stdin 输入
            "-ar", str(self.sample_rate),  # 重采样
            "-ac", str(self.channels),  # 单声道
            "-f", "s16le",  # 输出格式: 16 位整数
            "-acodec", "pcm_s16le",
            "pipe:1"  # 输出到 stdout
        ]
        return cmd
    
    def start_capture(self) -> None:
        """
        启动音频捕获
        """
        if self._running.is_set():
            logger.warning("Audio capture already running")
            return
        
        try:
            # 启动 scrcpy
            scrcpy_cmd = self._build_scrcpy_command()
            logger.info(f"Starting scrcpy: {' '.join(scrcpy_cmd)}")
            
            self._scrcpy_process = subprocess.Popen(
                scrcpy_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            # 启动 ffmpeg 进行转码
            ffmpeg_cmd = self._build_ffmpeg_command()
            logger.info(f"Starting ffmpeg: {' '.join(ffmpeg_cmd)}")
            
            self._ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=self._scrcpy_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            self._running.set()
            logger.info("Audio capture started")
            
        except FileNotFoundError as e:
            raise AudioCaptureError(f"scrcpy or ffmpeg not found: {e}")
        except Exception as e:
            raise AudioCaptureError(f"Failed to start audio capture: {e}")
    
    def get_audio_stream(self) -> Generator[bytes, None, None]:
        """
        获取音频流生成器
        
        Yields:
            bytes: 音频数据块 (16kHz, 16bit, 单声道 PCM)
        """
        if not self._running.is_set():
            raise AudioCaptureError("Audio capture not started")
        
        chunk_size = config.AUDIO_CONFIG["chunk_size"]
        
        while self._running.is_set():
            try:
                data = self._ffmpeg_process.stdout.read(chunk_size)
                if data:
                    yield data
                else:
                    # 检查进程是否异常退出
                    if self._scrcpy_process.poll() is not None:
                        logger.error("scrcpy process terminated")
                        break
            except Exception as e:
                logger.error(f"Error reading audio stream: {e}")
                break
    
    def stop_capture(self) -> None:
        """
        停止音频捕获
        """
        if not self._running.is_set():
            return
        
        logger.info("Stopping audio capture...")
        self._running.clear()
        
        # 终止进程
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._ffmpeg_process.kill()
        
        if self._scrcpy_process:
            try:
                self._scrcpy_process.terminate()
                self._scrcpy_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._scrcpy_process.kill()
        
        logger.info("Audio capture stopped")
    
    def is_running(self) -> bool:
        """检查是否正在捕获"""
        return self._running.is_set()
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start_capture()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop_capture()


def create_audio_capture(device_id: Optional[str] = None) -> AudioCapture:
    """
    创建音频捕获器工厂函数
    
    Args:
        device_id: 设备 ID
        
    Returns:
        AudioCapture 实例
    """
    return AudioCapture(device_id)