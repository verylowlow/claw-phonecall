#!/usr/bin/env python3
"""
火山引擎 ASR 客户端
实时语音识别
"""

import requests
import json
import uuid
import time
import base64
import queue
import threading
from typing import Optional, Callable


class VolcanoASR:
    """火山引擎ASR客户端"""
    
    def __init__(self, app_id: str, access_token: str, resource_id: str = "volc.seedasr.auc"):
        """
        初始化ASR客户端
        
        Args:
            app_id: 应用ID
            access_token: 访问令牌
            resource_id: 资源ID (模型)
        """
        self.app_id = app_id
        self.access_token = access_token
        self.resource_id = resource_id
        
        self.submit_url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
        self.query_url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
        
        self.is_recognizing = False
        self.result_queue = queue.Queue()
        
        # 配置
        self.config = {
            "format": "wav",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "codec": "raw"
        }
    
    def submit_audio(self, audio_data: bytes, request_id: str = None) -> str:
        """
        提交音频进行识别
        
        Args:
            audio_data: 音频数据 (bytes)
            request_id: 请求ID
            
        Returns:
            task_id用于后续查询
        """
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        # Base64编码
        audio_b64 = base64.b64encode(audio_data).decode('utf-8')
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Api-App-Key": self.app_id,
            "X-Api-Access-Key": self.access_token,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1"
        }
        
        data = {
            "user": {"uid": "openclaw"},
            "audio": {
                "format": "wav",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "codec": "raw",
                "content": audio_b64
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True
            }
        }
        
        response = requests.post(
            self.submit_url,
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            return request_id
        else:
            raise Exception(f"提交失败: {response.text}")
    
    def query_result(self, request_id: str) -> Optional[str]:
        """
        查询识别结果
        
        Args:
            request_id: 请求ID
            
        Returns:
            识别文本 或 None
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Api-App-Key": self.app_id,
            "X-Api-Access-Key": self.access_token,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id
        }
        
        response = requests.post(
            self.query_url,
            headers=headers,
            json={},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 1000:  # 成功
                return result.get("result", {}).get("text", "")
            elif result.get("code") == 1002:  # 处理中
                return None
            else:
                raise Exception(f"识别错误: {result.get('message', 'unknown')}")
        
        return None
    
    def recognize(self, audio_data: bytes, timeout: int = 10) -> Optional[str]:
        """
        同步识别音频
        
        Args:
            audio_data: 音频数据
            timeout: 超时时间(秒)
            
        Returns:
            识别文本
        """
        # 提交
        task_id = self.submit_audio(audio_data)
        
        # 轮询结果
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.query_result(task_id)
            if result is not None:
                return result
            time.sleep(0.5)
        
        raise Exception("识别超时")
    
    def start_stream_recognition(self):
        """开始流式识别"""
        self.is_recognizing = True
    
    def stop_stream_recognition(self):
        """停止流式识别"""
        self.is_recognizing = False


class StreamASRHandler:
    """流式ASR处理器 - 带VAD集成"""
    
    def __init__(self, asr_client: VolcanoASR, vad, audio_buffer):
        """
        初始化
        
        Args:
            asr_client: ASR客户端
            vad: VAD检测器
            audio_buffer: 音频缓冲区
        """
        self.asr = asr_client
        self.vad = vad
        self.buffer = audio_buffer
        
        self.is_processing = False
        self.last_result = ""
        
    def process_audio(self, audio_chunk: bytes) -> Optional[str]:
        """
        处理音频chunk
        
        Args:
            audio_chunk: 音频数据
            
        Returns:
            识别结果 或 None
        """
        if not self.is_processing:
            return None
        
        # VAD检测
        status = self.vad.update(audio_chunk)
        
        # 开始说话，开始录音
        if status == "start":
            self.buffer.start_recording()
        
        # 说话中，继续录音
        elif status == "speaking":
            self.buffer.add(audio_chunk)
        
        # 停止说话，提交识别
        elif status == "stop":
            if self.buffer.get_duration() > 0.3:  # 至少300ms
                audio = self.buffer.stop_recording()
                try:
                    result = self.asr.recognize(audio, timeout=5)
                    if result:
                        self.last_result = result
                        return result
                except Exception as e:
                    print(f"识别错误: {e}")
            else:
                self.buffer.clear()
        
        return None


class ASRResultHandler:
    """ASR结果处理器 - 处理识别结果"""
    
    def __init__(self):
        self.on_result = None
        self.on_error = None
    
    def handle(self, result: str):
        """处理识别结果"""
        if not result:
            return
        
        # 清理结果
        result = result.strip()
        
        if self.on_result:
            self.on_result(result)
    
    def set_callback(self, on_result: Callable, on_error: Callable = None):
        """设置回调"""
        self.on_result = on_result
        self.on_error = on_error


def create_asr_client(config: dict) -> VolcanoASR:
    """
    创建ASR客户端
    
    Args:
        config: 配置字典
        
    Returns:
        ASR客户端实例
    """
    return VolcanoASR(
        app_id=config.get("app_id", ""),
        access_token=config.get("access_token", ""),
        resource_id=config.get("resource_id", "volc.seedasr.auc")
    )


if __name__ == "__main__":
    import sys
    
    # 测试
    if len(sys.argv) < 3:
        print("用法: python asr_client.py <app_id> <access_token>")
        sys.exit(1)
    
    app_id = sys.argv[1]
    access_token = sys.argv[2]
    
    # 创建客户端
    asr = VolcanoASR(app_id, access_token)
    
    # 读取测试音频
    import wave
    with wave.open("test.wav", "rb") as f:
        audio_data = f.readframes(f.getnframes())
    
    print("开始识别...")
    try:
        result = asr.recognize(audio_data)
        print(f"识别结果: {result}")
    except Exception as e:
        print(f"识别失败: {e}")