#!/usr/bin/env python3
"""
火山引擎 TTS 客户端
文字转语音
"""

import requests
import json
import uuid
import time
import base64
import queue
import threading
import subprocess
from typing import Optional, Callable
from pathlib import Path


class VolcanoTTS:
    """火山引擎TTS客户端"""
    
    def __init__(self, app_id: str, access_token: str, voice: str = "xiaoxiao"):
        """
        初始化TTS客户端
        
        Args:
            app_id: 应用ID
            access_token: 访问令牌
            voice: 发音人
        """
        self.app_id = app_id
        self.access_token = access_token
        self.voice = voice
        
        self.api_url = "https://openspeech.bytedance.com/api/v2/tts"
        
    def synthesize(self, text: str, output_file: str = None) -> bytes:
        """
        合成语音
        
        Args:
            text: 要转换的文本
            output_file: 输出文件路径 (可选)
            
        Returns:
            音频数据 (MP3)
        """
        request_id = str(uuid.uuid4())
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Api-App-Key": self.app_id,
            "X-Api-Request-Id": request_id
        }
        
        data = {
            "app": {
                "appid": self.app_id,
                "token": self.access_token,
                "cluster": "volcengine_streaming_common"
            },
            "user": {
                "uid": "openclaw"
            },
            "audio": {
                "format": "mp3",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "codec": "raw",
                "volume": 100,
                "speed": 1.0  # 语速
            },
            "request": {
                "reqid": request_id,
                "text": text,
                "text_type": "plain",
                "operation": "submit",
                "voice": self.voice
            }
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("code") == 1000:
                audio_data = base64.b64decode(result["data"]["audio"])
                
                # 保存到文件
                if output_file:
                    with open(output_file, "wb") as f:
                        f.write(audio_data)
                
                return audio_data
            else:
                raise Exception(f"TTS失败: {result.get('message', 'unknown')}")
        else:
            raise Exception(f"请求失败: {response.status_code}")
    
    def synthesize_stream(self, text: str, callback: Callable[[bytes], None]):
        """
        流式合成并播放
        
        Args:
            text: 要转换的文本
            callback: 音频数据回调 (边合成边播放)
        """
        audio_data = self.synthesize(text)
        if callback:
            callback(audio_data)
    
    def play_audio(self, audio_data: bytes, device_serial: str = None):
        """
        通过ADB播放音频到手机
        
        Args:
            audio_data: 音频数据
            device_serial: 设备序列号
        """
        import tempfile
        import os
        
        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(audio_data)
            temp_file = f.name
        
        try:
            remote_path = "/sdcard/Download/tts_output.mp3"
            
            # 推送到手机
            cmd = f"adb -s {device_serial} push {temp_file} {remote_path}"
            subprocess.run(cmd, shell=True, check=False)
            
            # 使用MediaPlayer播放
            cmd = f"adb -s {device_serial} shell am start -n com.google.android.music/.MusicPlayerActivity -d file://{remote_path}"
            subprocess.run(cmd, shell=True, check=False)
            
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file)
            except:
                pass


class StreamingTTS:
    """流式TTS - 支持长文本"""
    
    def __init__(self, tts_client: VolcanoTTS, max_length: int = 500):
        """
        初始化流式TTS
        
        Args:
            tts_client: TTS客户端
            max_length: 单次最大字符数
        """
        self.tts = tts_client
        self.max_length = max_length
    
    def split_text(self, text: str) -> list:
        """拆分长文本"""
        # 按句子拆分
        import re
        
        # 标点符号分割
        sentences = re.split(r'([。！？.!?])', text)
        
        result = []
        current = ""
        
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else "")
            
            if len(current) + len(sentence) <= self.max_length:
                current += sentence
            else:
                if current:
                    result.append(current)
                current = sentence
        
        if current:
            result.append(current)
        
        return result
    
    def synthesize(self, text: str, output_file: str = None) -> bytes:
        """
        合成文本 (自动拆分长文本)
        
        Args:
            text: 要转换的文本
            output_file: 输出文件
            
        Returns:
            合并的音频数据
        """
        parts = self.split_text(text)
        
        all_audio = []
        for part in parts:
            try:
                audio = self.tts.synthesize(part)
                all_audio.append(audio)
            except Exception as e:
                print(f"部分合成失败: {e}")
        
        # 合并
        result = b''.join(all_audio)
        
        if output_file:
            with open(output_file, "wb") as f:
                f.write(result)
        
        return result
    
    def play(self, text: str, device_serial: str = None):
        """合成并播放"""
        audio = self.synthesize(text)
        self.tts.play_audio(audio, device_serial)


class TTSWithCallback(TTS):
    """带回调的TTS"""
    
    def __init__(self, app_id: str, access_token: str, voice: str = "xiaoxiao"):
        super().__init__(app_id, access_token, voice)
        self.on_start = None
        self.on_progress = None
        self.on_complete = None
    
    def synthesize(self, text: str, output_file: str = None) -> bytes:
        if self.on_start:
            self.on_start()
        
        result = super().synthesize(text, output_file)
        
        if self.on_complete:
            self.on_complete(result)
        
        return result


def create_tts_client(config: dict) -> VolcanoTTS:
    """
    创建TTS客户端
    
    Args:
        config: 配置字典
        
    Returns:
        TTS客户端实例
    """
    return VolcanoTTS(
        app_id=config.get("app_id", ""),
        access_token=config.get("access_token", ""),
        voice=config.get("voice", "xiaoxiao")
    )


if __name__ == "__main__":
    # 测试
    if len(sys.argv) < 3:
        print("用法: python tts_player.py <app_id> <access_token>")
        sys.exit(1)
    
    app_id = sys.argv[1]
    access_token = sys.argv[2]
    
    # 创建客户端
    tts = VolcanoTTS(app_id, access_token)
    
    # 测试
    text = "您好，我是AI助手，请问有什么可以帮您的？"
    print(f"合成文本: {text}")
    
    try:
        audio = tts.synthesize(text, "/tmp/tts_test.mp3")
        print(f"成功，音频大小: {len(audio)} bytes")
        print("已保存到 /tmp/tts_test.mp3")
    except Exception as e:
        print(f"合成失败: {e}")