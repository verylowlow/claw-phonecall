#!/usr/bin/env python3
"""
Edge TTS 客户端 (免费)
文字转语音
"""

import asyncio
import tempfile
import os
import sys
import subprocess
from typing import Optional, Callable
from pathlib import Path

# 尝试导入 edge_tts
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    print("警告: edge-tts 未安装, 请运行: pip install edge-tts")


class EdgeTTS:
    """Edge TTS 客户端"""
    
    # 可用的语音列表
    VOICES = {
        # 中文语音
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",        # 晓晓 (女声)
        "xiaoyi": "zh-CN-XiaoyiNeural",            # 晓伊 (女声)
        "yunjian": "zh-CN-YunjianNeural",          # 云健 (男声)
        "yunxi": "zh-CN-YunxiNeural",              # 云希 (男声)
        "yunyang": "zh-CN-YunyangNeural",          # 云扬 (男声)
        "xiaomei": "zh-CN-XiaomeiNeural",          # 晓梅 (女声)
        "xiaorui": "zh-CN-XiaoruiNeural",          # 晓睿 (女声)
        "xiaoshuang": "zh-CN-XiaoshuangNeural",    # 晓双 (女声)
        # 英文语音
        "jenny": "en-US-JennyNeural",             # Jenny (女声)
        "guy": "en-US-GuyNeural",                   # Guy (男声)
        "aria": "en-US-AriaNeural",                 # Aria (女声)
    }
    
    def __init__(self, voice: str = "xiaoxiao", rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%"):
        """
        初始化TTS客户端
        
        Args:
            voice: 发音人 (见VOICES)
            rate: 语速, 如 "+10%", "-10%", "+0%"
            pitch: 音调, 如 "+10Hz", "-5Hz", "+0Hz"
            volume: 音量, 如 "+10%", "-10%", "+0%"
        """
        self.voice = self.VOICES.get(voice, self.VOICES["xiaoxiao"])
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        
        if not EDGE_TTS_AVAILABLE:
            raise ImportError("edge-tts 未安装, 请运行: pip install edge-tts")
    
    async def _synthesize_async(self, text: str, output_file: str) -> str:
        """
        异步合成语音
        
        Args:
            text: 要转换的文本
            output_file: 输出文件路径
            
        Returns:
            输出文件路径
        """
        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume
        )
        
        await communicate.save(output_file)
        return output_file
    
    def synthesize(self, text: str, output_file: str = None) -> str:
        """
        合成语音
        
        Args:
            text: 要转换的文本
            output_file: 输出文件路径 (可选)
            
        Returns:
            音频文件路径
        """
        if not EDGE_TTS_AVAILABLE:
            raise ImportError("edge-tts 未安装, 请运行: pip install edge-tts")
        
        # 如果没有指定输出文件，创建临时文件
        if output_file is None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                output_file = f.name
        
        # 运行异步合成
        asyncio.run(self._synthesize_async(text, output_file))
        
        return output_file
    
    def synthesize_to_bytes(self, text: str) -> bytes:
        """
        合成语音返回字节
        
        Args:
            text: 要转换的文本
            
        Returns:
            音频数据 (MP3)
        """
        if not EDGE_TTS_AVAILABLE:
            raise ImportError("edge-tts 未安装, 请运行: pip install edge-tts")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            temp_file = f.name
        
        try:
            asyncio.run(self._synthesize_async(text, temp_file))
            
            with open(temp_file, "rb") as f:
                audio_data = f.read()
            
            return audio_data
        finally:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    def play_audio(self, audio_data_or_file, device_serial: str = None):
        """
        通过ADB播放音频到手机
        
        Args:
            audio_data_or_file: 音频数据(bytes)或文件路径(str)
            device_serial: 设备序列号
        """
        # 保存到临时文件
        if isinstance(audio_data_or_file, bytes):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                f.write(audio_data_or_file)
                temp_file = f.name
        else:
            temp_file = audio_data_or_file
        
        try:
            remote_path = "/sdcard/Download/tts_output.mp3"
            
            # 推送到手机
            if device_serial:
                cmd = f"adb -s {device_serial} push {temp_file} {remote_path}"
            else:
                cmd = f"adb push {temp_file} {remote_path}"
            subprocess.run(cmd, shell=True, check=False)
            
            # 使用MediaPlayer播放
            if device_serial:
                cmd = f"adb -s {device_serial} shell am start -n com.google.android.music/.MusicPlayerActivity -d file://{remote_path}"
            else:
                cmd = f"adb shell am start -n com.google.android.music/.MusicPlayerActivity -d file://{remote_path}"
            subprocess.run(cmd, shell=True, check=False)
            
        finally:
            # 清理临时文件
            try:
                if isinstance(audio_data_or_file, bytes):
                    os.unlink(temp_file)
            except:
                pass
    
    def play(self, text: str, device_serial: str = None):
        """
        合成并播放
        
        Args:
            text: 要转换的文本
            device_serial: 设备序列号
        """
        audio_file = self.synthesize(text)
        self.play_audio(audio_file, device_serial)


class StreamingTTS:
    """流式TTS - 支持长文本"""
    
    def __init__(self, tts_client: EdgeTTS, max_length: int = 500):
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
    
    def synthesize(self, text: str, output_file: str = None) -> str:
        """
        合成文本 (自动拆分长文本)
        
        Args:
            text: 要转换的文本
            output_file: 输出文件
            
        Returns:
            音频文件路径
        """
        parts = self.split_text(text)
        
        # 创建临时文件存储合并结果
        if output_file is None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                output_file = f.name
        
        # 合并所有MP3文件
        with open(output_file, 'wb') as outfile:
            for part in parts:
                try:
                    part_file = self.tts.synthesize(part)
                    with open(part_file, 'rb') as infile:
                        outfile.write(infile.read())
                    os.unlink(part_file)
                except Exception as e:
                    print(f"部分合成失败: {e}")
        
        return output_file
    
    def play(self, text: str, device_serial: str = None):
        """合成并播放"""
        audio_file = self.synthesize(text)
        self.tts.play_audio(audio_file, device_serial)


def create_tts_client(config: dict = None) -> EdgeTTS:
    """
    创建TTS客户端
    
    Args:
        config: 配置字典 (可选)
        
    Returns:
        TTS客户端实例
    """
    config = config or {}
    
    return EdgeTTS(
        voice=config.get("voice", "xiaoxiao"),
        rate=config.get("rate", "+0%"),
        pitch=config.get("pitch", "+0Hz"),
        volume=config.get("volume", "+0%")
    )


def list_available_voices():
    """列出可用的语音"""
    return EdgeTTS.VOICES


if __name__ == "__main__":
    if not EDGE_TTS_AVAILABLE:
        print("请先安装 edge-tts:")
        print("  pip install edge-tts")
        sys.exit(1)
    
    # 测试
    text = "您好，我是AI助手，请问有什么可以帮您的？"
    print(f"合成文本: {text}")
    print(f"可用语音: {list(EdgeTTS.VOICES.keys())}")
    
    # 创建客户端
    tts = EdgeTTS(voice="xiaoxiao")
    
    try:
        output_file = tts.synthesize(text, "/tmp/tts_test.mp3")
        print(f"成功，已保存到: {output_file}")
    except Exception as e:
        print(f"合成失败: {e}")