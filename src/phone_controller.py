"""
AI Phone Agent - 手机通话控制器模块
PhoneController: 通过 ADB 控制安卓手机的拨号、接听、挂断、状态监控
"""

import subprocess
import threading
import time
import logging
from typing import Optional, Callable, Dict, Any
from enum import IntEnum
from dataclasses import dataclass

from . import config

logger = logging.getLogger(__name__)


class CallState(IntEnum):
    """通话状态枚举"""
    IDLE = 0      # 闲置
    RINGING = 1   # 响铃
    OFFHOOK = 2   # 通话中


@dataclass
class PhoneEvent:
    """电话事件数据类"""
    event_type: str  # 'incoming', 'outgoing', 'answered', 'hungup', 'state_changed'
    phone_number: Optional[str] = None
    state: Optional[CallState] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class PhoneController:
    """
    手机通话控制器
    通过 ADB 实现对安卓手机的通话控制
    """
    
    def __init__(self, device_id: Optional[str] = None):
        """
        初始化通话控制器
        
        Args:
            device_id: 安卓设备 ID，用于多手机控制。None 表示默认设备。
        """
        self.device_id = device_id
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self._last_state: Optional[CallState] = None
        self._callbacks: Dict[str, Callable] = {}
        
        logger.info(f"PhoneController initialized for device: {device_id or 'default'}")
    
    def _build_adb_command(self, command: str) -> list:
        """
        构建 ADB 命令
        
        Args:
            command: shell 命令
            
        Returns:
            命令列表
        """
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["shell", command])
        return cmd
    
    def _run_adb_command(self, command: str, timeout: int = None) -> tuple:
        """
        执行 ADB 命令
        
        Args:
            command: shell 命令
            timeout: 超时时间（秒）
            
        Returns:
            (returncode, stdout, stderr)
        """
        if timeout is None:
            timeout = config.ADB_CONFIG["timeout"]
        
        cmd = self._build_adb_command(command)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"ADB command timeout: {command}")
            return -1, "", "Timeout"
        except Exception as e:
            logger.error(f"ADB command error: {e}")
            return -1, "", str(e)
    
    def get_call_state(self) -> CallState:
        """
        获取当前通话状态
        
        Returns:
            CallState: 当前通话状态
        """
        cmd = "dumpsys telephony.registry | grep mCallState"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        if returncode != 0:
            logger.warning(f"Failed to get call state: {stderr}")
            return CallState.IDLE
        
        # 解析输出: mCallState=0
        try:
            for line in stdout.split('\n'):
                if 'mCallState' in line:
                    state = int(line.split('=')[1].strip())
                    return CallState(state)
        except (IndexError, ValueError) as e:
            logger.error(f"Failed to parse call state: {e}, output: {stdout}")
        
        return CallState.IDLE
    
    def get_incoming_number(self) -> Optional[str]:
        """
        获取来电号码
        
        Returns:
            来电号码，如果没有则返回 None
        """
        # 方法1: 从 telephony.registry 获取
        cmd = "dumpsys telephony.registry | grep mIncomingNumber"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        if returncode == 0 and stdout:
            try:
                # mIncomingNumber = 13800138000
                number = stdout.split('=')[1].strip()
                if number and number != "":
                    return number
            except IndexError:
                pass
        
        # 方法2: 从 logcat 获取
        cmd = "logcat -d -b radio | grep -E 'RING|incoming' | tail -5"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        # 解析来电号码
        if returncode == 0:
            for line in stdout.split('\n'):
                if 'RING' in line or 'incoming' in line:
                    # 尝试从日志中提取号码
                    parts = line.split()
                    for part in parts:
                        if part.isdigit() and len(part) >= 7:
                            return part
        
        return None
    
    def dial(self, phone_number: str) -> bool:
        """
        拨打电话
        
        Args:
            phone_number: 电话号码
            
        Returns:
            bool: 是否成功发起呼叫
        """
        # 清理号码格式
        phone_number = phone_number.strip().replace(" ", "").replace("-", "")
        
        # 使用 am start 启动拨号界面
        cmd = f"am start -a android.intent.action.DIAL tel:{phone_number}"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        if returncode == 0:
            logger.info(f"Dialing {phone_number}...")
            # 注意：这只是打开拨号界面，实际呼叫需要用户点击拨打按钮
            # 或者使用 service call 触发实际呼叫
            time.sleep(1)
            return True
        else:
            logger.error(f"Failed to dial {phone_number}: {stderr}")
            return False
    
    def dial_and_call(self, phone_number: str) -> bool:
        """
        拨打电话并自动呼叫
        
        Args:
            phone_number: 电话号码
            
        Returns:
            bool: 是否成功
        """
        # 先打开拨号盘
        if not self.dial(phone_number):
            return False
        
        # 等待拨号盘打开
        time.sleep(1)
        
        # 模拟点击拨打按钮 (KEYCODE_CALL = 5)
        cmd = "input keyevent 5"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        if returncode == 0:
            logger.info(f"Call initiated to {phone_number}")
            return True
        else:
            logger.warning(f"Keyevent 5 failed, trying service call: {stderr}")
            # 备选方案: 使用 service call
            cmd = "service call phone 1"
            returncode, stdout, stderr = self._run_adb_command(cmd)
            return returncode == 0
    
    def answer(self) -> bool:
        """
        接听电话 (模拟耳机接听键)
        
        Returns:
            bool: 是否成功接听
        """
        # 先唤醒屏幕
        cmd = "input keyevent 26"
        self._run_adb_command(cmd)
        time.sleep(0.3)
        
        # 模拟接听按键 (KEYCODE_CALL = 5)
        cmd = "input keyevent 5"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        if returncode == 0:
            logger.info("Call answered")
            return True
        else:
            # 备选: service call
            logger.warning(f"Keyevent 5 failed, trying service call: {stderr}")
            cmd = "service call phone 2"
            returncode, stdout, stderr = self._run_adb_command(cmd)
            return returncode == 0
    
    def hangup(self) -> bool:
        """
        挂断电话
        
        Returns:
            bool: 是否成功挂断
        """
        # 模拟挂断按键 (KEYCODE_ENDCALL = 6)
        cmd = "input keyevent 6"
        returncode, stdout, stderr = self._run_adb_command(cmd)
        
        if returncode == 0:
            logger.info("Call hung up")
            return True
        else:
            # 备选: service call
            logger.warning(f"Keyevent 6 failed, trying service call: {stderr}")
            cmd = "service call phone 3"
            returncode, stdout, stderr = self._run_adb_command(cmd)
            return returncode == 0
    
    def _monitor_loop(self):
        """后台监控循环"""
        poll_interval = config.ADB_CONFIG["poll_interval"]
        
        while not self._stop_monitoring.is_set():
            try:
                current_state = self.get_call_state()
                
                # 检测状态变化
                if current_state != self._last_state:
                    logger.info(f"Call state changed: {self._last_state} -> {current_state}")
                    
                    # 触发回调
                    if self._last_state == CallState.IDLE and current_state == CallState.RINGING:
                        # 来电
                        phone_number = self.get_incoming_number()
                        event = PhoneEvent(
                            event_type="incoming",
                            phone_number=phone_number,
                            state=current_state
                        )
                        if self._callbacks.get("on_incoming"):
                            self._callbacks["on_incoming"](event)
                            
                    elif self._last_state == CallState.RINGING and current_state == CallState.OFFHOOK:
                        # 接通
                        event = PhoneEvent(event_type="answered", state=current_state)
                        if self._callbacks.get("on_answered"):
                            self._callbacks["on_answered"](event)
                            
                    elif current_state == CallState.IDLE and self._last_state in [CallState.RINGING, CallState.OFFHOOK]:
                        # 挂断
                        event = PhoneEvent(event_type="hungup", state=current_state)
                        if self._callbacks.get("on_hungup"):
                            self._callbacks["on_hungup"](event)
                    
                    # 通用状态变化回调
                    if self._callbacks.get("on_state_changed"):
                        event = PhoneEvent(event_type="state_changed", state=current_state)
                        self._callbacks["on_state_changed"](event)
                    
                    self._last_state = current_state
                    
            except Exception as e:
                logger.error(f"Monitor error: {e}")
            
            time.sleep(poll_interval)
        
        logger.info("Phone monitoring stopped")
    
    def start_monitoring(
        self,
        on_incoming: Optional[Callable] = None,
        on_answered: Optional[Callable] = None,
        on_hungup: Optional[Callable] = None,
        on_state_changed: Optional[Callable] = None
    ):
        """
        启动后台通话状态监控
        
        Args:
            on_incoming: 来电时回调，参数: PhoneEvent
            on_answered: 接通时回调
            on_hungup: 挂断时回调
            on_state_changed: 状态变化时回调
        """
        # 注册回调
        if on_incoming:
            self._callbacks["on_incoming"] = on_incoming
        if on_answered:
            self._callbacks["on_answered"] = on_answered
        if on_hungup:
            self._callbacks["on_hungup"] = on_hungup
        if on_state_changed:
            self._callbacks["on_state_changed"] = on_state_changed
        
        # 启动监控线程
        self._stop_monitoring.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info("Phone monitoring started")
    
    def stop_monitoring(self):
        """停止后台监控"""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("Phone monitoring stopped")
    
    def is_idle(self) -> bool:
        """检查手机是否空闲"""
        return self.get_call_state() == CallState.IDLE
    
    def wait_for_state(self, target_state: CallState, timeout: float = 30) -> bool:
        """
        等待进入目标状态
        
        Args:
            target_state: 目标状态
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否成功进入目标状态
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.get_call_state() == target_state:
                return True
            time.sleep(config.ADB_CONFIG["poll_interval"])
        return False


def create_phone_controller(device_id: Optional[str] = None) -> PhoneController:
    """
    创建手机控制器工厂函数
    
    Args:
        device_id: 设备 ID
        
    Returns:
        PhoneController 实例
    """
    return PhoneController(device_id)