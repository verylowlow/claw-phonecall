"""
火山引擎流式 ASR 模块
使用 WebSocket 协议进行实时语音识别
"""

import asyncio
import gzip
import json
import struct
import uuid
import threading
import logging
import queue
from typing import Optional, Generator, AsyncGenerator
import websocket

from . import config

logger = logging.getLogger(__name__)


class VolcEngineASR:
    """
    火山引擎流式 ASR
    支持双向流式识别（实时返回）
    """

    # 双向流式优化版接口
    ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

    # 认证配置
    APP_KEY = None
    ACCESS_TOKEN = None
    SECRET_KEY = None

    # 资源 ID
    RESOURCE_ID = "volc.bigasr.sauc.duration"

    def __init__(self, app_key: str = None, access_token: str = None, secret_key: str = None):
        self.APP_KEY = app_key or config.VOLC_ASR_CONFIG.get("app_key", "")
        self.ACCESS_TOKEN = access_token or config.VOLC_ASR_CONFIG.get("access_token", "")
        self.SECRET_KEY = secret_key or config.VOLC_ASR_CONFIG.get("secret_key", "")

        self._ws = None
        self._connected = threading.Event()
        self._sequence = 0
        self._running = False
        self._lock = threading.Lock()

    def _build_auth_headers(self) -> dict:
        return {
            "X-Api-App-Key": self.APP_KEY,
            "X-Api-Access-Key": self.ACCESS_TOKEN,
            "X-Api-Resource-Id": self.RESOURCE_ID,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }

    def _build_request_params(self) -> dict:
        return {
            "user": {
                "uid": "phone_agent",
                "did": "phone_agent_device",
                "platform": "Linux",
                "sdk_version": "1.0.0",
                "app_version": "1.0.0"
            },
            "audio": {
                "format": "wav",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "codec": "raw",
                "language": "zh-CN"
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_ddc": False,
                "enable_punc": True,
                "result_type": "full",
                "end_window_size": 800,  # 800ms 静音判停
            }
        }

    def _build_header(self, message_type: int, flags: int = 0,
                      serialization: int = 1, compression: int = 1) -> bytes:
        version = 1
        header_size = 1
        byte0 = (version << 4) | header_size
        byte1 = (message_type << 4) | flags
        byte2 = (serialization << 4) | compression
        byte3 = 0
        return bytes([byte0, byte1, byte2, byte3])

    def _build_full_request(self, params: dict) -> bytes:
        header = self._build_header(message_type=1, flags=0, serialization=1, compression=1)
        payload = json.dumps(params).encode('utf-8')
        payload_compressed = gzip.compress(payload)
        payload_size = struct.pack('>I', len(payload_compressed))
        return header + payload_size + payload_compressed

    def _build_audio_request(self, audio_data: bytes, is_last: bool = False) -> bytes:
        flags = 2 if is_last else 0

        # 添加 WAV 头，使服务端能正确解析
        wav_header = self._create_wav_header(len(audio_data))
        audio_with_header = wav_header + audio_data

        header = self._build_header(message_type=2, flags=flags, serialization=0, compression=1)
        audio_compressed = gzip.compress(audio_with_header)
        payload_size = struct.pack('>I', len(audio_compressed))
        return header + payload_size + audio_compressed

    def _create_wav_header(self, data_size: int) -> bytes:
        """创建 WAV 文件头（不写入实际数据）"""
        import wave
        import io
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            # 不写入任何数据，只创建正确的头
            # WAV 头格式: RIFF header + fmt chunk + data chunk
            # 手动构建正确的头
        # 读取并修改 data chunk 大小
        header = buffer.getvalue()
        # 修改 data chunk 的大小（offset 40-43，4字节）
        import struct
        data_size_bytes = struct.pack('<I', data_size)
        header = header[:40] + data_size_bytes + header[44:]
        return header

    def _parse_response(self, data: bytes) -> Optional[dict]:
        if len(data) < 12:
            return None

        try:
            byte1 = data[1]
            message_type = (byte1 >> 4) & 0x0F

            # 如果不是响应消息类型，跳过
            if message_type != 9:
                return None

            # Sequence number
            sequence = struct.unpack('>I', data[4:8])[0]

            # Payload
            payload_size = struct.unpack('>I', data[8:12])[0]
            if len(data) < 12 + payload_size:
                return None

            payload = data[12:12 + payload_size]

            # 解压
            try:
                payload = gzip.decompress(payload)
            except:
                pass

            # 解析 JSON
            result = json.loads(payload.decode('utf-8'))
            return result

        except Exception as e:
            logger.error(f"Parse response error: {e}")
            return None

    def connect(self) -> bool:
        """建立 WebSocket 连接"""
        if not config.volc_asr_configured():
            logger.error(
                "火山 ASR 凭证未配置：请在环境中设置 VOLC_ASR_APP_KEY、"
                "VOLC_ASR_ACCESS_TOKEN、VOLC_ASR_SECRET_KEY（可写入项目根目录 .env）"
            )
            return False
        try:
            headers = self._build_auth_headers()
            self._ws = websocket.create_connection(
                self.ASR_URL,
                header=headers,
                timeout=30
            )
            self._connected.set()
            logger.info("Connected to VolcEngine ASR")

            # 发送初始配置
            params = self._build_request_params()
            request_data = self._build_full_request(params)
            self._ws.send(request_data)

            # 等待响应
            self._ws.settimeout(5)
            try:
                response = self._ws.recv()
                result = self._parse_response(response)
                if result:
                    logger.info(f"ASR initialized: {result}")
            except:
                pass

            return True
        except Exception as e:
            logger.error(f"Failed to connect to ASR: {e}")
            return False

    def send_audio_stream(self, audio_chunk: bytes, is_last: bool = False) -> Optional[str]:
        """
        发送音频块并获取识别结果（同步版本）

        Args:
            audio_chunk: PCM 音频数据
            is_last: 是否是最后一包

        Returns:
            识别文本
        """
        if not self._connected.is_set():
            if not self.connect():
                return None

        try:
            with self._lock:
                # 发送音频
                request_data = self._build_audio_request(audio_chunk, is_last)
                self._ws.send(request_data)

                # 接收响应（设置短超时以实现实时返回）
                self._ws.settimeout(2)
                try:
                    while True:
                        response = self._ws.recv()
                        result = self._parse_response(response)
                        if result and 'result' in result:
                            text = result['result'].get('text', '')
                            return text
                except:
                    pass

                return None

        except Exception as e:
            logger.error(f"ASR stream error: {e}")
            return None

    async def send_audio_stream_async(self, audio_chunk: bytes, is_last: bool = False) -> Optional[str]:
        """异步版本的发送音频"""
        return self.send_audio_stream(audio_chunk, is_last)

    def close(self):
        """关闭连接"""
        if self._ws:
            try:
                self._ws.close()
            except:
                pass
        self._connected.clear()


class StreamingASRHandler:
    """
    流式 ASR 处理器
    整合 AudioCapture 和 VolcEngineASR，实现真正的实时语音识别
    """

    def __init__(self):
        self._asr = None
        self._running = False
        self._result_queue = queue.Queue(maxsize=100)

    def start(self):
        """启动流式 ASR"""
        self._asr = VolcEngineASR()
        if self._asr.connect():
            self._running = True
            return True
        return False

    def process_audio_stream(self, audio_stream: Generator[bytes, None, None],
                            chunk_duration_ms: int = 200) -> Generator[str, None, None]:
        """
        处理实时音频流

        Args:
            audio_stream: 音频流生成器
            chunk_duration_ms: 每次发送的音频时长（毫秒）

        Yields:
            识别文本
        """
        if not self._running or not self._asr:
            logger.error("ASR not started")
            return

        # 计算每次发送的字节数 (16000Hz * 2bytes * 1channel * ms / 1000)
        bytes_per_chunk = 16000 * 2 * chunk_duration_ms // 1000
        buffer = b''

        for chunk in audio_stream:
            buffer += chunk

            # 累积足够的音频后发送
            while len(buffer) >= bytes_per_chunk:
                audio_to_send = buffer[:bytes_per_chunk]
                buffer = buffer[bytes_per_chunk:]

                # 发送并获取结果
                result = self._asr.send_audio_stream(audio_to_send, is_last=False)
                if result:
                    yield result

    def stop(self):
        """停止流式 ASR"""
        self._running = False
        if self._asr:
            self._asr.close()
            self._asr = None


class VolcASRManager:
    """
    火山引擎 ASR 管理器
    提供与本地 ASR 相同的接口
    支持流式和批量两种模式
    """

    def __init__(self):
        self._streaming_handler: Optional[StreamingASRHandler] = None
        self._asr = None
        self._initialized = False

    def load_model(self) -> None:
        """初始化 ASR"""
        if self._initialized:
            return

        try:
            # 流式处理器（需要时再启动）
            self._streaming_handler = StreamingASRHandler()
            logger.info("VolcEngine ASR handler initialized")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize VolcEngine ASR: {e}")

    def transcribe(self, audio_chunk: bytes, language: str = "zh") -> str:
        """
        转写音频（批量模式）

        Args:
            audio_chunk: PCM 音频数据

        Returns:
            识别文本
        """
        if not self._initialized:
            self.load_model()

        # 懒加载
        if self._asr is None:
            self._asr = VolcEngineASR()

        # 确保有连接
        if not self._asr._connected.is_set():
            self._asr.connect()

        try:
            result = self._asr.send_audio_stream(audio_chunk, is_last=True)
            return result or ""
        except Exception as e:
            logger.error(f"ASR transcription error: {e}")
            return ""

    def transcribe_stream(self, audio_stream: Generator[bytes, None, None]) -> Generator[str, None, None]:
        """
        流式转写（实时模式）

        Args:
            audio_stream: 音频流生成器

        Yields:
            识别文本
        """
        if not self._initialized:
            self.load_model()

        if self._streaming_handler is None:
            self._streaming_handler = StreamingASRHandler()

        if not self._streaming_handler._running:
            if not self._streaming_handler.start():
                logger.error("Failed to start streaming ASR")
                return

        yield from self._streaming_handler.process_audio_stream(audio_stream)

    def close(self):
        """关闭 ASR"""
        if self._streaming_handler:
            self._streaming_handler.stop()
            self._streaming_handler = None
        if self._asr:
            self._asr.close()
            self._asr = None
        self._initialized = False


def create_volc_asr() -> VolcASRManager:
    """创建火山引擎 ASR 管理器"""
    return VolcASRManager()