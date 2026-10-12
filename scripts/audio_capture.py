#!/usr/bin/env python3
"""
音频采集模块 - ALSA/FIFO方案
通过ADB管道实时采集手机音频
"""

import subprocess
import os
import socket
import threading
import time
import queue
import numpy as np
from typing import Optional, Callable


class AudioCapture:
    """音频采集类 - ALSA/FIFO方案"""
    
    def __init__(self, device_serial: str):
        """
        初始化音频采集
        
        Args:
            device_serial: 设备序列号
        """
        self.device_serial = device_serial
        self.fifo_path = "/data/local/tmp/audio_pipe"
        self.is_capturing = False
        self.audio_queue = queue.Queue(maxsize=100)
        self.forward_port = 18888  # ADB端口转发
        
    def setup(self) -> bool:
        """
        在手机上设置音频管道
        
        Returns:
            是否设置成功
        """
        # 创建FIFO管道
        self._adb_command(f"shell mkfifo {self.fifo_path}")
        
        # 确保目录存在
        self._adb_command("shell mkdir -p /data/local/tmp")
        
        # 启动ALSA录制
        # 使用arecord录制系统音频 (需要root)
        cmd = (
            f"shell su -c '"
            f"arecord -D hw:0,0 "
            f"-f S16_LE "
            f"-r 16000 "
            f"-c 1 "
            f"-t raw "
            f"{self.fifo_path} &'"
        )
        self._adb_command(cmd, check=False)
        
        # 设置端口转发
        self._adb_command(f"forward tcp:{self.forward_port} localabstract:{self.fifo_path.replace('/data/local/tmp/', '')}")
        
        return True
    
    def start(self) -> bool:
        """
        开始采集音频
        
        Returns:
            是否成功开始
        """
        if self.is_capturing:
            return False
        
        # 先设置管道
        self.setup()
        
        self.is_capturing = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        return True
    
    def stop(self):
        """停止采集"""
        self.is_capturing = False
        if hasattr(self, 'capture_thread'):
            self.capture_thread.join(timeout=2)
        
        # 停止录音
        self._adb_command("shell pkill -f arecord", check=False)
        
        # 移除端口转发
        self._adb_command(f"forward --remove tcp:{self.forward_port}", check=False)
    
    def _capture_loop(self):
        """采集循环 - 通过netcat读取音频"""
        try:
            # 使用netcat连接
            process = subprocess.Popen(
                ["nc", "localhost", str(self.forward_port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            buffer_size = 4096  # 16位 1通道 16kHz = 32KB/秒
            
            while self.is_capturing:
                data = process.stdout.read(buffer_size)
                if data:
                    self.audio_queue.put(data)
                else:
                    break
                    
        except Exception as e:
            print(f"音频采集错误: {e}")
        finally:
            process.terminate()
    
    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[bytes]:
        """
        获取一段音频数据
        
        Args:
            timeout: 超时时间
            
        Returns:
            音频数据(bytes) 或 None
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _adb_command(self, command: str, check: bool = True) -> str:
        """执行ADB命令"""
        prefix = f"-s {self.device_serial} " if self.device_serial else ""
        cmd = f"adb {prefix}{command}"
        
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, check=check
        )
        return result.stdout.strip()
    
    def get_audio_level(self) -> float:
        """获取当前音频电平 (0.0-1.0)"""
        try:
            chunk = self.audio_queue.queue[0] if not self.audio_queue.empty() else None
            if chunk:
                # 计算RMS
                audio_data = np.frombuffer(chunk, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_data ** 2))
                level = min(rms / 32768.0 * 2, 1.0)
                return level
        except:
            pass
        return 0.0


class AudioPlayer:
    """音频播放类 - 通过手机端播放"""
    
    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self.is_playing = False
        self.play_process = None
        
    def play_audio_file(self, audio_path: str) -> bool:
        """
        播放音频文件
        
        Args:
            audio_path: 音频文件路径 (电脑端)
            
        Returns:
            是否成功
        """
        # 先推送文件到手机
        remote_path = "/sdcard/Download/temp_audio.mp3"
        subprocess.run(
            f"adb -s {self.device_serial} push {audio_path} {remote_path}",
            shell=True, check=False
        )
        
        # 使用termux播放 (如果有termux)
        try:
            self._adb_command(
                f"shell am start -n com.termux/com.termux.app.TermuxActivity "
                f"-e argument '-e play {remote_path}'"
            )
            return True
        except:
            pass
        
        # 使用自带播放器
        try:
            self._adb_command(
                f"shell am start -a android.intent.action.VIEW -d file://{remote_path}"
            )
            return True
        except:
            pass
        
        return False
    
    def play_tts_stream(self, audio_data: bytes) -> bool:
        """
        流式播放音频数据
        
        Args:
            audio_data: 音频数据 (PCM/MP3)
            
        Returns:
            是否成功
        """
        # 保存到临时文件
        local_path = "/tmp/tts_output.mp3"
        with open(local_path, 'wb') as f:
            f.write(audio_data)
        
        return self.play_audio_file(local_path)
    
    def stop(self):
        """停止播放"""
        # 停止当前播放
        self._adb_command("shell input keyevent 85", check=False)  # 暂停/播放
        self._adb_command("shell am force-stop com.google.android.music", check=False)
    
    def set_volume(self, level: float):
        """
        设置音量 (0.0-1.0)
        
        Args:
            level: 音量级别
        """
        # 媒体音量
        level_int = int(level * 15)
        self._adb_command(f"shell media volume --show --stream 3 --set {level_int}", check=False)
    
    def _adb_command(self, command: str, check: bool = True) -> str:
        prefix = f"-s {self.device_serial} " if self.device_serial else ""
        cmd = f"adb {prefix}{command}"
        
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, check=check
        )
        return result.stdout.strip()


class AudioManager:
    """音频管理器 - 统一管理采集和播放"""
    
    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self.capture = AudioCapture(device_serial)
        self.player = AudioPlayer(device_serial)
    
    def start(self):
        """启动音频系统"""
        self.capture.start()
    
    def stop(self):
        """停止音频系统"""
        self.capture.stop()
        self.player.stop()
    
    def get_audio(self, timeout: float = 1.0) -> Optional[bytes]:
        """获取音频数据"""
        return self.capture.get_audio_chunk(timeout)
    
    def play(self, audio_data: bytes):
        """播放音频"""
        self.player.play_tts_stream(audio_data)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python audio_capture.py <设备序列号>")
        sys.exit(1)
    
    serial = sys.argv[1]
    print(f"初始化音频系统: {serial}")
    
    manager = AudioManager(serial)
    manager.start()
    
    print("开始采集音频 (按Ctrl+C停止)...")
    try:
        while True:
            audio = manager.get_audio(0.5)
            if audio:
                print(f"收到音频: {len(audio)} bytes, 电平: {manager.capture.get_audio_level():.2f}")
    except KeyboardInterrupt:
        print("\n停止采集")
        manager.stop()