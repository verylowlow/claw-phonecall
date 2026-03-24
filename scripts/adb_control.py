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
    
    def __init__(self, device_serial: str, use_root: bool = True):
        """
        初始化ADB控制
        
        Args:
            device_serial: 设备序列号
            use_root: 是否使用root权限执行命令 (input命令需要)
        """
        self.device_serial = device_serial
        self.use_root = use_root
        self._verify_connection()
    
    def _run_command(self, command: str, check: bool = True, use_shell: bool = True) -> str:
        """执行ADB命令"""
        if self.device_serial:
            adb_cmd = f"adb -s {self.device_serial}"
        else:
            adb_cmd = "adb"
        
        # 如果需要root权限，用su -c包装
        if self.use_root and command.startswith("shell input"):
            full_cmd = f"{adb_cmd} shell 'su -c \"{command}\"'"
        else:
            full_cmd = f"{adb_cmd} {command}"
        
        result = subprocess.run(
            full_cmd, 
            shell=use_shell, 
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
        # 接听电话
        self._run_command("shell input keyevent 5", check=False)
        return True
    
    def reject_call(self) -> bool:
        """
        拒接电话
        
        Returns:
            是否成功拒接
        """
        # 拒接电话
        self._run_command("shell input keyevent 6", check=False)
        return True
    
    def end_call(self) -> bool:
        """
        结束通话
        
        Returns:
            是否成功结束
        """
        # 挂断电话
        self._run_command("shell input keyevent 6", check=False)
        return True
    
    def press_digit(self, digit: str) -> bool:
        """
        按数字键
        
        Args:
            digit: 数字 0-9, *, #
            
        Returns:
            是否成功按键
        """
        keyevent_map = {
            '0': '7', '1': '8', '2': '9', '3': '10',
            '4': '11', '5': '12', '6': '13',
            '7': '14', '8': '15', '9': '16',
            '*': '17', '#': '18'
        }
        
        if digit not in keyevent_map:
            return False
        
        self._run_command(f"shell input keyevent {keyevent_map[digit]}", check=False)
        return True
    
    def press_home(self) -> bool:
        """按Home键"""
        self._run_command("shell input keyevent 3", check=False)
        return True
    
    def press_power(self) -> bool:
        """按电源键"""
        self._run_command("shell input keyevent 26", check=False)
        return True
    
    def swipe_up(self) -> bool:
        """上滑解锁"""
        self._run_command("shell input swipe 500 1500 500 500", check=False)
        return True
    
    def tap(self, x: int, y: int) -> bool:
        """
        点击屏幕指定位置
        
        Args:
            x: X坐标
            y: Y坐标
            
        Returns:
            是否成功点击
        """
        self._run_command(f"shell input tap {x} {y}", check=False)
        return True
    
    def text_input(self, text: str) -> bool:
        """
        输入文本
        
        Args:
            text: 要输入的文本
            
        Returns:
            是否成功输入
        """
        # 需要转义特殊字符
        text = text.replace(" ", "%s")
        self._run_command(f'shell input text "{text}"', check=False)
        return True
    
    def take_screenshot(self, save_path: str) -> bool:
        """
        截屏
        
        Args:
            save_path: 保存路径
            
        Returns:
            是否成功截屏
        """
        self._run_command(f"shell screencap -p {save_path}", check=False)
        return True
    
    def open_app(self, package_name: str) -> bool:
        """
        打开应用
        
        Args:
            package_name: 包名
            
        Returns:
            是否成功打开
        """
        self._run_command(f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1", check=False)
        return True
    
    def close_app(self, package_name: str) -> bool:
        """
        强制停止应用
        
        Args:
            package_name: 包名
            
        Returns:
            是否成功关闭
        """
        self._run_command(f"shell am force-stop {package_name}", check=False)
        return True
    
    def get_screen_state(self) -> bool:
        """
        获取屏幕状态
        
        Returns:
            屏幕是否亮着
        """
        try:
            result = self._run_command("shell dumpsys power | grep 'mScreenOn'", check=False)
            return "mScreenOn=true" in result
        except:
            return False
    
    def wake_screen(self) -> bool:
        """唤醒屏幕"""
        self.press_power()
        time.sleep(0.5)
        return True


def create_adb_controller(device_serial: str = None, use_root: bool = True) -> ADBControl:
    """
    创建ADB控制器
    
    Args:
        device_serial: 设备序列号 (None则自动选择第一个设备)
        use_root: 是否使用root权限
        
    Returns:
        ADBControl实例
    """
    if device_serial is None:
        # 获取第一个设备
        result = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            # 取第二行第一个空格前的字符串
            device_serial = lines[1].split()[0]
    
    return ADBControl(device_serial, use_root=use_root)


if __name__ == "__main__":
    import sys
    
    # 测试
    if len(sys.argv) < 2:
        print("用法: python adb_control.py <设备序列号>")
        sys.exit(1)
    
    device = sys.argv[1]
    
    # 创建控制器
    adb = ADBControl(device)
    
    # 测试连接
    if adb.is_device_connected():
        print(f"设备已连接: {device}")
        print(f"使用Root权限: {adb.use_root}")
    else:
        print("设备未连接")