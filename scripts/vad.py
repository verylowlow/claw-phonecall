#!/usr/bin/env python3
"""
VAD (Voice Activity Detection) 模块
检测语音活动，确定说话状态
"""

import numpy as np
import webrtcvad
import collections


class VADDetector:
    """语音活动检测器"""
    
    def __init__(self, sample_rate: int = 16000, frame_duration: int = 30):
        """
        初始化VAD
        
        Args:
            sample_rate: 采样率 (8000, 16000, 32000, 48000)
            frame_duration: 帧长度 (10, 20, 30 ms)
        """
        self.sample_rate = sample_rate
        self.frame_duration = frame_duration
        self.vad = webrtcvad.Vad(2)  # 激进模式
        
        # 状态相关
        self.is_speaking = False
        self.silence_count = 0
        self.speech_count = 0
        
        # 配置参数
        self.silence_threshold = 20  # 连续多少帧静音认为对方停止说话
        self.speech_threshold = 3     # 连续多少帧有声音认为开始说话
        
    def is_speech(self, audio_chunk: bytes) -> bool:
        """
        检测音频chunk中是否有语音
        
        Args:
            audio_chunk: 原始音频数据
            
        Returns:
            是否有语音
        """
        try:
            # WebRTC VAD
            return self.vad.is_speech(audio_chunk, self.sample_rate)
        except:
            # 回退到能量检测
            return self._energy_detection(audio_chunk)
    
    def _energy_detection(self, audio_chunk: bytes) -> bool:
        """能量检测作为备选"""
        try:
            audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_data ** 2))
            # 阈值判断
            return rms > 500
        except:
            return False
    
    def update(self, audio_chunk: bytes) -> str:
        """
        更新VAD状态
        
        Args:
            audio_chunk: 音频数据
            
        Returns:
            状态: "speaking", "silence", "start", "stop"
        """
        has_speech = self.is_speech(audio_chunk)
        
        if has_speech:
            self.speech_count += 1
            self.silence_count = 0
            
            if not self.is_speaking and self.speech_count >= self.speech_threshold:
                # 开始说话
                self.is_speaking = True
                self.speech_count = 0
                return "start"
            
            if self.is_speaking:
                return "speaking"
        else:
            self.silence_count += 1
            self.speech_count = 0
            
            if self.is_speaking and self.silence_count >= self.silence_threshold:
                # 停止说话
                self.is_speaking = False
                self.silence_count = 0
                return "stop"
            
            if not self.is_speaking:
                return "silence"
        
        # 正在说话
        if self.is_speaking:
            return "speeding"
        
        return "silence"
    
    def reset(self):
        """重置状态"""
        self.is_speaking = False
        self.silence_count = 0
        self.speech_count = 0


class VADWithCallback(VADDetector):
    """带回调的VAD - 用于异步处理"""
    
    def __init__(self, sample_rate: int = 16000, frame_duration: int = 30):
        super().__init__(sample_rate, frame_duration)
        
        self.on_speech_start = None
        self.on_speech_end = None
        self.on_silence = None
    
    def process(self, audio_chunk: bytes) -> str:
        """
        处理音频并触发回调
        
        Returns:
            状态
        """
        status = self.update(audio_chunk)
        
        # 触发回调
        if status == "start" and self.on_speech_start:
            self.on_speech_start()
        elif status == "stop" and self.on_speech_end:
            self.on_speech_end()
        elif status == "silence" and self.on_silence:
            # 只有在说话后的静音才触发
            if self.silence_count == 1:
                self.on_silence()
        
        return status


class AudioBuffer:
    """音频缓冲区 - 用于缓存音频进行识别"""
    
    def __init__(self, max_size: int = 100):
        """
        初始化缓冲区
        
        Args:
            max_size: 最大缓存帧数
        """
        self.max_size = max_size
        self.buffer = collections.deque(maxlen=max_size)
        self.is_recording = False
    
    def add(self, audio_chunk: bytes):
        """添加音频"""
        self.buffer.append(audio_chunk)
    
    def get_all(self) -> bytes:
        """获取所有音频"""
        return b''.join(self.buffer)
    
    def clear(self):
        """清空缓冲区"""
        self.buffer.clear()
    
    def get_duration(self) -> float:
        """获取缓冲区音频时长(秒)"""
        if not self.buffer:
            return 0
        # 假设16kHz, 16bit, mono
        total_bytes = sum(len(chunk) for chunk in self.buffer)
        return total_bytes / (16000 * 2)  # 2 bytes per sample
    
    def start_recording(self):
        """开始录音"""
        self.is_recording = True
        self.clear()
    
    def stop_recording(self) -> bytes:
        """停止录音并返回"""
        self.is_recording = False
        return self.get_all()


class SilenceFiller:
    """静音填充器 - 检测到长时间静音时填充话术"""
    
    def __init__(self, phrases: list = None):
        """
        初始化
        
        Args:
            phrases: 填充话术列表
        """
        self.phrases = phrases or [
            "嗯，好的，请讲",
            "我在听",
            "嗯嗯",
            "请说"
        ]
        self.last_fill_time = 0
        self.fill_interval = 3  # 最小填充间隔(秒)
        self.phrase_index = 0
    
    def should_fill(self, silence_duration: float, vad_status: str) -> bool:
        """
        是否应该填充
        
        Args:
            silence_duration: 静音持续时间
            vad_status: VAD状态
            
        Returns:
            是否填充
        """
        import time
        
        # 只有在静音状态才考虑填充
        if vad_status != "silence":
            return False
        
        # 检查时间间隔
        current_time = time.time()
        if current_time - self.last_fill_time < self.fill_interval:
            return False
        
        # 静音超过2秒
        if silence_duration >= 2.0:
            return True
        
        return False
    
    def get_next_phrase(self) -> str:
        """
        获取下一个填充话术
        
        Returns:
            话术文本
        """
        import time
        
        phrase = self.phrases[self.phrase_index]
        self.phrase_index = (self.phrase_index + 1) % len(self.phrases)
        self.last_fill_time = time.time()
        
        return phrase


def create_vad_detector(mode: int = 2) -> VADDetector:
    """
    创建VAD检测器
    
    Args:
        mode: 激进模式 (0-3)
        
    Returns:
        VADDetector实例
    """
    vad = VADDetector()
    vad.vad.set_mode(mode)
    return vad


if __name__ == "__main__":
    # 测试
    import wave
    
    # 生成测试音频
    sample_rate = 16000
    duration = 3  # 秒
    frequency = 440  # Hz
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
    
    # 创建VAD
    vad = create_vad_detector()
    
    # 分帧处理
    frame_size = int(sample_rate * 0.03)  # 30ms
    frames = []
    
    for i in range(0, len(audio) - frame_size, frame_size):
        frame = audio[i:i+frame_size]
        frames.append(frame.tobytes())
    
    # 检测
    print("测试音频帧检测:")
    for i, frame in enumerate(frames[:50]):  # 前50帧
        has_speech = vad.is_speech(frame)
        status = vad.update(frame)
        if has_speech:
            print(f"  帧{i}: 有语音 ({status})")
    
    print(f"检测完成, 说话状态: {vad.is_speaking}")