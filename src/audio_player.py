"""
AI Phone Agent - 音频播放模块
AudioPlayer: 通过物理声卡将音频播放到手机
"""

import pyaudio
import threading
import queue
import logging
import numpy as np
from typing import Optional, Generator
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


class AudioPlayerError(Exception):
    """音频播放异常"""
    pass


class AudioPlayer:
    """
    音频播放器
    使用 PyAudio 通过物理声卡播放音频
    """
    
    def __init__(self, output_device_index: Optional[int] = None):
        """
        初始化音频播放器
        
        Args:
            output_device_index: 输出设备索引，None 为默认设备
        """
        self.output_device_index = output_device_index
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
        self._running = threading.Event()
        self._play_thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=50)
        
        # 从配置获取参数
        self.sample_rate = config.AUDIO_CONFIG["sample_rate"]
        self.channels = config.AUDIO_CONFIG["channels"]
        self.buffer_size = config.AUDIO_CONFIG["buffer_size"]
        
        logger.info(f"AudioPlayer initialized with device: {output_device_index or 'default'}")
    
    def _init_pyaudio(self) -> None:
        """初始化 PyAudio"""
        if self._pyaudio is not None:
            return
        
        try:
            self._pyaudio = pyaudio.PyAudio()
            logger.info("PyAudio initialized")
        except Exception as e:
            raise AudioPlayerError(f"Failed to initialize PyAudio: {e}")
    
    def _get_output_devices(self) -> list:
        """获取可用输出设备列表"""
        if self._pyaudio is None:
            self._init_pyaudio()
        
        devices = []
        for i in range(self._pyaudio.get_device_count()):
            info = self._pyaudio.get_device_info_by_index(i)
            if info['maxOutputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxOutputChannels']
                })
        return devices
    
    def list_output_devices(self) -> None:
        """列出可用输出设备（调试用）"""
        devices = self._get_output_devices()
        logger.info("Available output devices:")
        for d in devices:
            logger.info(f"  [{d['index']}] {d['name']} (max {d['channels']} channels)")
    
    def open_stream(self) -> None:
        """打开音频流"""
        if self._stream is not None:
            logger.warning("Audio stream already open")
            return
        
        self._init_pyaudio()
        
        try:
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.buffer_size,
                start=False
            )
            logger.info("Audio stream opened")
        except Exception as e:
            raise AudioPlayerError(f"Failed to open audio stream: {e}")
    
    def start(self) -> None:
        """
        启动音频播放
        """
        if self._running.is_set():
            logger.warning("Audio player already running")
            return
        
        if self._stream is None:
            self.open_stream()
        
        # 启动播放线程
        self._running.set()
        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._play_thread.start()
        
        # 启动音频流
        self._stream.start_stream()
        
        logger.info("Audio player started")
    
    def _play_loop(self) -> None:
        """播放循环"""
        while self._running.is_set():
            try:
                # 从队列获取音频数据，超时则继续
                audio_data = self._audio_queue.get(timeout=0.1)
                
                if audio_data is None:  # 结束信号
                    break
                
                # 写入音频流
                if self._stream and self._stream.is_active():
                    self._stream.write(audio_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in play loop: {e}")
                break
        
        logger.info("Play loop exited")
    
    def play(self, audio_data: bytes) -> None:
        """
        播放音频数据
        
        Args:
            audio_data: PCM 音频数据 (16kHz, 16bit, 单声道)
        """
        if not self._running.is_set():
            raise AudioPlayerError("Audio player not started")
        
        try:
            self._audio_queue.put_nowait(audio_data)
        except queue.Full:
            logger.warning("Audio queue full, dropping data")
    
    def play_bytes(self, audio_data: bytes) -> None:
        """播放音频字节数据（play 的别名）"""
        self.play(audio_data)
    
    def play_numpy(self, audio_array: np.ndarray) -> None:
        """
        播放 NumPy 音频数组
        
        Args:
            audio_array: NumPy 数组，dtype=int16
        """
        # 转换为字节
        audio_data = audio_array.astype(np.int16).tobytes()
        self.play(audio_data)
    
    def play_stream(self, audio_generator: Generator[bytes, None, None]) -> None:
        """
        流式播放音频生成器
        
        Args:
            audio_generator: 音频数据生成器
        """
        for chunk in audio_generator:
            if not self._running.is_set():
                break
            self.play(chunk)
    
    def flush(self) -> None:
        """刷新播放队列，等待当前音频播放完成"""
        # 等待队列清空
        while not self._audio_queue.empty():
            import time
            time.sleep(0.1)
    
    def stop(self) -> None:
        """
        停止音频播放
        """
        if not self._running.is_set():
            return
        
        logger.info("Stopping audio player...")
        self._running.clear()
        
        # 发送结束信号
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            pass
        
        # 等待播放线程结束
        if self._play_thread:
            self._play_thread.join(timeout=2)
        
        # 停止流
        if self._stream:
            try:
                if self._stream.is_active():
                    self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")
            self._stream = None
        
        logger.info("Audio player stopped")
    
    def close(self) -> None:
        """关闭播放器，释放资源"""
        self.stop()
        
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
            self._pyaudio = None
        
        logger.info("Audio player closed")
    
    def is_running(self) -> bool:
        """检查是否正在播放"""
        return self._running.is_set()
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
    
    def __del__(self):
        """析构函数"""
        try:
            self.close()
        except:
            pass


def create_audio_player(output_device_index: Optional[int] = None) -> AudioPlayer:
    """
    创建音频播放器工厂函数
    
    Args:
        output_device_index: 输出设备索引
        
    Returns:
        AudioPlayer 实例
    """
    return AudioPlayer(output_device_index)