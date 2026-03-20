#!/usr/bin/env python3
"""
ADB手机控制模块
负责通过ADB命令控制安卓手机完成电话操作
"""

import subprocess
import time
import re
from typing import Optional, Dict


class ADBControl:
    """ADB手机控制类"""
    
    def __init__(self, device_serial: str):
        """
        初始化ADB控制
        
        Args:
            device_serial: 设备序列号
        """
        self.device_serial = device_serial
        self._verify_connection()
    
    def _run_command(self, command: str, check: bool = True) -> str:
        """执行ADB命令"""
        if self.device_serial:
            cmd = f"adb -s {self.device_serial} {command}"
        else:
            cmd = f"adb {command}"
        
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            check=check
        )
        return result.stdout.strip()
    
    def _verify_connection(self):
        """验证设备连接"""
        devices = self._run_command("devices -l", check=False)
        if self.device_serial not in devices:
            raise ConnectionError(f"设备未连接: {self.device_serial}")
    
    def is_device_connected(self) -> bool:
        """检查设备是否连接"""
        try:
            self._run_command("get-state", check=False)
            return True
        except:
            return False
    
    def dial(self, phone_number: str) -> bool:
        """
        拨打电话
        
        Args:
            phone_number: 电话号码
            
        Returns:
            是否成功拨出
        """
        # 清理号码格式
        phone_number = phone_number.replace(" ", "").replace("-", "")
        
        # 使用Intent拨打电话
        self._run_command(
            f'shell am start -a android.intent.action.CALL -d tel:{phone_number}',
            check=False
        )
        return True
    
    def answer_call(self) -> bool:
        """
        接听电话
        
        Returns:
            是否成功接听
        """
        # 方法1: 模拟按键
        try:
            self._run_command("shell input keyevent 5", check=False)
            return True
        except:
            pass
        
        # 方法2: 使用service call (需要root)
        try:
            self._run_command(
                "shell service call phone 1 s16 '+861000'",
                check=False
            )
            return True
        except:
            pass
        
        return False
    
    def hangup(self) -> bool:
        """
        挂断电话
        
        Returns:
            是否成功挂断
        """
        # 方法1: 模拟按键
        try:
            self._run_command("shell input keyevent 6", check=False)
            return True
        except:
            pass
        
        # 方法2: 结束通话 (需要root)
        try:
            self._run_command(
                "shell service call phone 11",
                check=False
            )
            return True
        except:
            pass
        
        return False
    
    def send_dtmf(self, digit: str) -> bool:
        """
        发送DTMF按键
        
        Args:
            digit: 按键数字 (0-9, *, #)
            
        Returns:
            是否发送成功
        """
        keyevent_map = {
            '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
            '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
            '*': 10, '#': 11
        }
        
        if digit not in keyevent_map:
            return False
        
        self._run_command(f"shell input keyevent {keyevent_map[digit]}", check=False)
        return True
    
    def get_call_state(self) -> str:
        """
        获取通话状态
        
        Returns:
            通话状态: idle, ringing, offhook, connected
        """
        # 方法1: 通过telecom服务查询
        try:
            result = self._run_command(
                "shell dumpsys telecom | grep -i 'CallState'",
                check=False
            )
            if "CONNECTED" in result:
                return "connected"
            elif "RINGING" in result:
                return "ringing"
            elif "OFFHOOK" in result:
                return "offhook"
        except:
            pass
        
        # 方法2: 通过Phone状态查询
        try:
            result = self._run_command(
                "shell dumpsys activity activities | grep mResumedActivity",
                check=False
            )
            if "DialtactsActivity" in result or "InCallActivity" in result:
                return "offhook"
        except:
            pass
        
        return "idle"
    
    def is_in_call(self) -> bool:
        """是否在通话中"""
        state = self.get_call_state()
        return state in ["ringing", "offhook", "connected"]
    
    def wait_for_answer(self, timeout: int = 30) -> bool:
        """
        等待对方接听
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            是否成功接听
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            state = self.get_call_state()
            if state == "connected":
                # 再等待1秒确保完全接通
                time.sleep(1)
                return True
            elif state == "idle":
                # 对方拒接或忙
                return False
            time.sleep(0.5)
        
        # 超时后检查状态
        return self.is_in_call()
    
    def press_home(self) -> bool:
        """返回主屏幕"""
        self._run_command("shell input keyevent 3", check=False)
        return True
    
    def unlock_screen(self) -> bool:
        """解锁屏幕"""
        # 唤醒屏幕
        self._run_command("shell input keyevent 26", check=False)
        time.sleep(0.3)
        # 滑动解锁
        self._run_command("shell input swipe 500 1500 500 500", check=False)
        return True
    
    def get_device_info(self) -> Dict:
        """获取设备信息"""
        info = {}
        
        # 型号
        try:
            info['model'] = self._run_command("shell getprop ro.product.model")
        except:
            info['model'] = "Unknown"
        
        # Android版本
        try:
            info['android_version'] = self._run_command("shell getprop ro.build.version.release")
        except:
            info['android_version'] = "Unknown"
        
        # 是否root
        try:
            result = self._run_command("shell su -c 'id'", check=False)
            info['rooted'] = "root" in result
        except:
            info['rooted'] = False
        
        return info
    
    def execute_shell(self, command: str) -> str:
        """执行Shell命令"""
        return self._run_command(f"shell {command}", check=False)


def list_devices() -> list:
    """列出已连接的设备"""
    result = subprocess.run(
        "adb devices",
        shell=True,
        capture_output=True,
        text=True
    )
    
    devices = []
    lines = result.stdout.strip().split('\n')[1:]  # 跳过标题行
    
    for line in lines:
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                devices.append({
                    'serial': parts[0],
                    'status': parts[1]
                })
    
    return devices


if __name__ == "__main__":
    # 测试
    devices = list_devices()
    print("已连接的设备:")
    for dev in devices:
        print(f"  - {dev['serial']} ({dev['status']})")
    
    if devices:
        adb = ADBControl(devices[0]['serial'])
        print(f"\n设备信息: {adb.get_device_info()}")