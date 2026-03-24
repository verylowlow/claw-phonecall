#!/usr/bin/env python3
"""
Claw Phone Call - 主入口
通过OpenClaw控制安卓手机完成电话呼出和语音交互
"""

import os
import sys
import yaml
import argparse
from pathlib import Path

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from scripts.adb_control import ADBControl, list_devices
from scripts.audio_capture import AudioManager
from scripts.vad import VADDetector, SilenceFiller
from scripts.asr_client import VolcanoASR, create_asr_client
from scripts.tts_player import EdgeTTS, create_tts_client
from scripts.dialog_manager import DialogManager, MultiCallManager


class PhoneCall:
    """电话控制主类"""
    
    def __init__(self, device_serial: str, config_path: str = None):
        """
        初始化电话控制
        
        Args:
            device_serial: 设备序列号
            config_path: 配置文件路径
        """
        self.device_serial = device_serial
        self.config = self._load_config(config_path)
        
        # 初始化组件
        self.adb = ADBControl(device_serial)
        self.audio = AudioManager(device_serial)
        self.vad = VADDetector()
        self.silence_filler = SilenceFiller()
        
        # ASR/TTS
        volc_config = self.config.get("volcengine", {})
        asr_config = volc_config.get("asr", {})
        tts_config = volc_config.get("tts", {})
        
        self.asr = create_asr_client(asr_config)
        self.tts = create_tts_client(tts_config)
        
        # 对话管理器
        self.dialog_manager = DialogManager(
            self.adb,
            self.audio,
            self.asr,
            self.tts,
            self.vad,
            self.config.get("dialog", {})
        )
        
    def _load_config(self, config_path: str = None) -> dict:
        """加载配置"""
        if config_path is None:
            config_path = Path(__file__).parent / "configs" / "settings.yaml"
        
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        
        return {}
    
    def dial(self, phone_number: str) -> bool:
        """
        拨打电话
        
        Args:
            phone_number: 电话号码
            
        Returns:
            是否成功拨出
        """
        return self.adb.dial(phone_number)
    
    def wait_for_answer(self, timeout: int = 30) -> bool:
        """
        等待对方接听
        
        Args:
            timeout: 超时时间
            
        Returns:
            是否成功接听
        """
        return self.adb.wait_for_answer(timeout)
    
    def answer_call(self) -> bool:
        """接听电话"""
        return self.adb.answer_call()
    
    def hangup(self) -> bool:
        """挂断电话"""
        return self.adb.hangup()
    
    def start_conversation(self, greeting: str = None):
        """
        开始对话
        
        Args:
            greeting: 开场白
        """
        self.dialog_manager.start_conversation(greeting)
    
    def run_full_call(self, phone_number: str, greeting: str = None) -> bool:
        """
        完整流程：拨号 -> 等待接听 -> 对话 -> 挂断
        
        Args:
            phone_number: 电话号码
            greeting: 开场白
            
        Returns:
            是否成功完成
        """
        # 拨号
        if not self.dial(phone_number):
            return False
        
        # 等待接听
        if not self.wait_for_answer():
            return False
        
        # 接听
        self.answer_call()
        
        # 开始对话
        self.start_conversation(greeting)
        
        return True
    
    def stop(self):
        """停止通话"""
        if self.dialog_manager:
            self.dialog_manager.stop()
        self.adb.hangup()
        self.audio.stop()
    
    def get_device_info(self) -> dict:
        """获取设备信息"""
        return self.adb.get_device_info()


class PhoneCallManager:
    """多设备电话管理器"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path
        self.devices = {}
        self.managers = {}
        
    def add_device(self, device_id: str, serial: str, phone_number: str = None):
        """
        添加设备
        
        Args:
            device_id: 设备ID
            serial: ADB序列号
            phone_number: 手机号
        """
        self.devices[device_id] = {
            "serial": serial,
            "phone_number": phone_number
        }
        self.managers[device_id] = PhoneCall(serial, self.config_path)
    
    def get_manager(self, device_id: str) -> PhoneCall:
        """获取设备管理器"""
        return self.managers.get(device_id)
    
    def dial_all(self, calls: list) -> dict:
        """
        同时拨打多个电话
        
        Args:
            calls: [(device_id, phone_number), ...]
            
        Returns:
            结果
        """
        results = {}
        for device_id, phone_number in calls:
            manager = self.managers.get(device_id)
            if manager:
                results[device_id] = manager.dial(phone_number)
        return results
    
    def dial_and_connect(self, calls: list, timeout: int = 30) -> dict:
        """
        拨打并等待接听
        
        Args:
            calls: [(device_id, phone_number), ...]
            timeout: 等待接听超时
            
        Returns:
            成功接通的设备列表
        """
        # 同时拨号
        self.dial_all(calls)
        
        # 等待接听
        connected = []
        for device_id, phone_number in calls:
            manager = self.managers.get(device_id)
            if manager and manager.wait_for_answer(timeout):
                manager.answer_call()
                connected.append(device_id)
        
        return connected


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Claw Phone Call - 安卓电话控制")
    parser.add_argument("-s", "--serial", help="设备序列号")
    parser.add_argument("-c", "--config", help="配置文件路径")
    parser.add_argument("command", nargs="?", help="命令: dial/call/list/info")
    parser.add_argument("args", nargs="*", help="命令参数")
    
    args = parser.parse_args()
    
    # 列出设备
    if args.command == "list":
        devices = list_devices()
        print("已连接的设备:")
        for dev in devices:
            print(f"  - {dev['serial']} ({dev['status']})")
        return
    
    # 需要设备序列号
    if not args.serial:
        print("错误: 请指定设备序列号 (-s)")
        print("使用 'list' 命令查看可用设备")
        return
    
    # 创建电话控制实例
    phone = PhoneCall(args.serial, args.config)
    
    # 执行命令
    if args.command == "dial" or args.command == "call":
        if not args.args:
            print("错误: 请指定电话号码")
            return
        
        phone_number = args.args[0]
        greeting = "您好，我是AI助手，请问有什么可以帮您？"
        
        print(f"开始呼叫: {phone_number}")
        
        if phone.run_full_call(phone_number, greeting):
            print("通话完成")
        else:
            print("通话失败")
    
    elif args.command == "info":
        info = phone.get_device_info()
        print("设备信息:")
        for key, value in info.items():
            print(f"  {key}: {value}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()