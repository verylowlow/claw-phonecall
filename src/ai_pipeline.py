"""
AI Phone Agent - AI 处理管道模块
AIPipeline: 整合 VAD + ASR + LLM + TTS 实现智能对话
"""

import asyncio
import threading
import queue
import logging
import time
import uuid
from typing import Optional, Callable, AsyncGenerator, Generator
from dataclasses import dataclass
from enum import Enum

from . import config
from .phone_controller import PhoneController, CallState, PhoneEvent
from .audio_capture import AudioCapture
from .audio_player import AudioPlayer
from .humanization import Humanization

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """管道状态"""
    IDLE = "idle"
    DIALING = "dialing"
    CONNECTING = "connecting"
    ACTIVE = "active"
    ENDING = "ending"
    ERROR = "error"


@dataclass
class Transcript:
    """对话转写"""
    text: str
    is_final: bool
    timestamp: float
    speaker: str  # "user" or "agent"


@dataclass
class PipelineEvent:
    """管道事件"""
    event_type: str
    data: any
    timestamp: float


class VADManager:
    """
    VAD (Voice Activity Detection) 管理器
    使用 Silero VAD 进行语音活动检测
    """
    
    def __init__(self):
        """初始化 VAD 管理器"""
        self._vad = None
        self._model_loaded = False
        self._lock = threading.Lock()
        
    def load_model(self) -> None:
        """加载 VAD 模型"""
        if self._model_loaded:
            return
        
        try:
            # 延迟导入，避免启动时卡顿
            from silero_vad import load_model, get_speech_timestamps
            
            logger.info("Loading Silero VAD model...")
            self._vad = load_model()
            self._model_loaded = True
            logger.info("Silero VAD model loaded")
        except Exception as e:
            logger.error(f"Failed to load VAD model: {e}")
            # 继续运行，使用简单能量检测作为后备
            self._model_loaded = False
    
    def detect_speech(self, audio_chunk: bytes) -> tuple:
        """
        检测语音
        
        Args:
            audio_chunk: PCM 音频数据
            
        Returns:
            tuple: (is_speech, speech_timestamps)
        """
        if not self._model_loaded or self._vad is None:
            # 后备：简单的能量检测
            import numpy as np
            audio = np.frombuffer(audio_chunk, dtype=np.int16)
            energy = np.abs(audio).mean() / 32768.0
            return energy > 0.05, []
        
        try:
            import numpy as np
            audio = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
            # 获取语音时间戳
            speech_timestamps = self._vad.get_speech_timestamps(
                audio,
                threshold=config.VAD_CONFIG["threshold"],
                min_speech_duration_ms=config.VAD_CONFIG["min_speech_duration_ms"],
                min_silence_duration_ms=config.VAD_CONFIG["min_silence_duration_ms"],
                speech_pad_ms=config.VAD_CONFIG["speech_pad_ms"]
            )
            
            is_speech = len(speech_timestamps) > 0
            return is_speech, speech_timestamps
        except Exception as e:
            logger.error(f"VAD detection error: {e}")
            return False, []


class ASRManager:
    """
    ASR (Automatic Speech Recognition) 管理器
    使用 Faster-Whisper 进行语音识别
    """
    
    def __init__(self):
        """初始化 ASR 管理器"""
        self._model = None
        self._model_loaded = False
        self._lock = threading.Lock()
        
    def load_model(self) -> None:
        """加载 ASR 模型"""
        if self._model_loaded:
            return
        
        try:
            from faster_whisper import WhisperModel
            
            logger.info(f"Loading Faster-Whisper model: {config.ASR_CONFIG['model_size']}")
            self._model = WhisperModel(
                config.ASR_CONFIG["model_size"],
                device=config.ASR_CONFIG["device"],
                compute_type="float16" if config.ASR_CONFIG["device"] == "cuda" else "int8"
            )
            self._model_loaded = True
            logger.info("Faster-Whisper model loaded")
        except Exception as e:
            logger.error(f"Failed to load ASR model: {e}")
            self._model_loaded = False
    
    def transcribe(self, audio_chunk: bytes, language: str = "zh") -> str:
        """
        转写音频
        
        Args:
            audio_chunk: PCM 音频数据
            language: 语言代码
            
        Returns:
            str: 转写文本
        """
        if not self._model_loaded or self._model is None:
            return ""
        
        try:
            import numpy as np
            audio = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
            segments, _ = self._model.transcribe(
                audio,
                language=language,
                vad_filter=True,
                vad_parameters=dict(
                    min_speech_duration_ms=config.VAD_CONFIG["min_speech_duration_ms"]
                )
            )
            
            text = " ".join([seg.text for seg in segments])
            return text.strip()
        except Exception as e:
            logger.error(f"ASR transcription error: {e}")
            return ""


class TTSManager:
    """
    TTS (Text-to-Speech) 管理器
    使用 Edge-TTS 进行语音合成
    """
    
    def __init__(self):
        """初始化 TTS 管理器"""
        self._voice = config.TTS_CONFIG["voice"]
        self._rate = config.TTS_CONFIG["rate"]
        self._pitch = config.TTS_CONFIG["pitch"]
        self._volume = config.TTS_CONFIG["volume"]
        
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            
        Yields:
            bytes: 音频数据块
        """
        try:
            import edge_tts
            import io
            
            communicate = edge_tts.Communicate(
                text,
                self._voice,
                rate=self._rate,
                pitch=self._pitch,
                volume=self._volume
            )
            
            # 收集音频数据
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            # 转换为 16kHz PCM
            if audio_data:
                # 使用 ffmpeg 转换采样率
                import subprocess
                ffmpeg_cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "webm", "-acodec", "opus", "-i", "pipe:0",
                    "-ar", str(config.AUDIO_CONFIG["sample_rate"]),
                    "-ac", str(config.AUDIO_CONFIG["channels"]),
                    "-f", "s16le", "-acodec", "pcm_s16le",
                    "pipe:1"
                ]
                
                proc = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                output, _ = proc.communicate(input=audio_data)
                
                # 分块输出
                chunk_size = config.AUDIO_CONFIG["chunk_size"]
                for i in range(0, len(output), chunk_size):
                    yield output[i:i+chunk_size]
                    
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
    
    def synthesize_sync(self, text: str) -> bytes:
        """
        同步合成语音
        
        Args:
            text: 要合成的文本
            
        Returns:
            bytes: 完整音频数据
        """
        import asyncio
        
        audio_chunks = []
        
        async def collect():
            async for chunk in self.synthesize(text):
                audio_chunks.append(chunk)
        
        asyncio.run(collect())
        return b"".join(audio_chunks)


class AIPipeline:
    """
    AI 处理管道
    整合所有组件实现完整的通话流程
    """
    
    def __init__(self, phone_controller: PhoneController):
        """
        初始化 AI 管道
        
        Args:
            phone_controller: 手机控制器实例
        """
        self.phone_controller = phone_controller
        self.state = PipelineState.IDLE
        
        # 组件
        self.vad = VADManager()
        self.asr = ASRManager()
        self.tts = TTSManager()
        # LLM 逻辑移至 OpenClaw 端，Python Skill 只负责硬件抽象
        self.humanization = Humanization()
        
        # 音频组件
        self.audio_capture: Optional[AudioCapture] = None
        self.audio_player: Optional[AudioPlayer] = None
        
        # 线程
        self._capture_thread: Optional[threading.Thread] = None
        self._process_thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        
        # 回调
        self._callbacks: dict = {}
        
        # 通话信息
        self.current_phone_number: Optional[str] = None
        self.call_start_time: Optional[float] = None
        
        logger.info("AIPipeline initialized")
    
    def load_models(self) -> None:
        """预加载模型"""
        logger.info("Loading AI models...")
        
        self.vad.load_model()
        self.asr.load_model()
        
        logger.info("AI models loaded")
    
    def set_audio_devices(self, capture: AudioCapture, player: AudioPlayer) -> None:
        """设置音频设备"""
        self.audio_capture = capture
        self.audio_player = player
    
    async def start_outbound_call(self, phone_number: str) -> bool:
        """
        发起外呼
        
        Args:
            phone_number: 电话号码
            
        Returns:
            bool: 是否成功发起呼叫
        """
        logger.info(f"Starting outbound call to {phone_number}")
        self.current_phone_number = phone_number
        self.state = PipelineState.DIALING
        
        # 拨号
        success = self.phone_controller.dial_and_call(phone_number)
        
        if success:
            self.state = PipelineState.CONNECTING
            # 等待对方接听
            if self.phone_controller.wait_for_state(CallState.OFFHOOK, timeout=60):
                return await self._start_active_call()
            else:
                logger.warning("Call not answered")
                self.state = PipelineState.IDLE
                return False
        else:
            logger.error("Failed to dial")
            self.state = PipelineState.ERROR
            return False
    
    async def handle_incoming_call(self, event: PhoneEvent) -> bool:
        """
        处理来电
        
        Args:
            event: 电话事件
            
        Returns:
            bool: 是否成功接听
        """
        logger.info(f"Handling incoming call from {event.phone_number}")
        self.current_phone_number = event.phone_number
        self.state = PipelineState.CONNECTING
        
        # 延迟接听
        await asyncio.sleep(config.CALL_CONFIG["answer_delay"])
        
        # 接听
        success = self.phone_controller.answer()
        
        if success:
            return await self._start_active_call()
        else:
            logger.error("Failed to answer call")
            self.state = PipelineState.ERROR
            return False
    
    async def _start_active_call(self) -> bool:
        """开始主动通话"""
        self.state = PipelineState.ACTIVE
        self.call_start_time = time.time()
        
        # 播放欢迎语
        welcome_msg = config.CALL_CONFIG["welcome_message"]
        logger.info(f"Playing welcome message: {welcome_msg}")
        
        # 异步播放欢迎语
        async for audio_chunk in self.tts.synthesize(welcome_msg):
            if self.audio_player:
                self.audio_player.play(audio_chunk)
        
        # 启动音频捕获和处理
        self._running.set()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        
        self._trigger_callback("on_call_start", {"phone_number": self.current_phone_number})
        
        return True
    
    def _capture_loop(self) -> None:
        """音频捕获循环"""
        if not self.audio_capture:
            return
        
        try:
            self.audio_capture.start_capture()
            
            for audio_chunk in self.audio_capture.get_audio_stream():
                if not self._running.is_set():
                    break
                
                # VAD 检测
                is_speech, _ = self.vad.detect_speech(audio_chunk)
                
                if is_speech:
                    self.humanization.on_speech_start()
                    
                    # 转写
                    text = self.asr.transcribe(audio_chunk)
                    if text:
                        transcript = Transcript(
                            text=text,
                            is_final=False,
                            timestamp=time.time(),
                            speaker="user"
                        )
                        self._trigger_callback("on_transcript", transcript)
                else:
                    self.humanization.on_speech_end(0)
                    
                    # 检查是否需要插入填充词
                    filler = self.humanization.get_filler()
                    if filler and self.audio_player:
                        # 播放填充词
                        filler_audio = self.tts.synthesize_sync(filler)
                        self.audio_player.play(filler_audio)
                        
        except Exception as e:
            logger.error(f"Capture loop error: {e}")
        finally:
            if self.audio_capture:
                self.audio_capture.stop_capture()
    
    async def end_call(self) -> None:
        """结束通话"""
        logger.info("Ending call...")
        self.state = PipelineState.ENDING
        self._running.clear()
        
        # 停止监控
        self.phone_controller.stop_monitoring()
        
        # 停止音频
        if self.audio_player:
            self.audio_player.stop()
        if self.audio_capture:
            self.audio_capture.stop_capture()
        
        # 等待线程结束
        if self._capture_thread:
            self._capture_thread.join(timeout=2)
        
        self.state = PipelineState.IDLE
        self._trigger_callback("on_call_end", {"duration": time.time() - self.call_start_time})
        
        logger.info("Call ended")
    
    def register_callback(self, event_type: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event_type] = callback
    
    def _trigger_callback(self, event_type: str, data: any) -> None:
        """触发回调"""
        if event_type in self._callbacks:
            try:
                self._callbacks[event_type](data)
            except Exception as e:
                logger.error(f"Callback error: {e}")


def create_ai_pipeline(phone_controller: PhoneController) -> AIPipeline:
    """
    创建 AI 管道
    
    Args:
        phone_controller: 手机控制器
        
    Returns:
        AIPipeline 实例
    """
    return AIPipeline(phone_controller)