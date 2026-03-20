#!/usr/bin/env python3
"""
对话管理器
管理电话对话的完整流程
"""

import time
import queue
import threading
from typing import Optional, Callable, Dict
from enum import Enum


class DialogState(Enum):
    """对话状态"""
    IDLE = "idle"
    DIALING = "dialing"
    WAITING = "waiting"
    CONNECTED = "connected"
    CONVERSING = "conversing"
    ENDING = "ending"
    FINISHED = "finished"


class DialogManager:
    """对话管理器"""
    
    def __init__(self, 
                 adb_control,
                 audio_manager,
                 asr_client,
                 tts_client,
                 vad_detector,
                 config: dict = None):
        """
        初始化对话管理器
        
        Args:
            adb_control: ADB控制
            audio_manager: 音频管理
            asr_client: ASR客户端
            tts_client: TTS客户端
            vad_detector: VAD检测器
            config: 配置
        """
        self.adb = adb_control
        self.audio = audio_manager
        self.asr = asr_client
        self.tts = tts
        self.vad = vad_detector
        
        self.config = config or {}
        
        # 配置参数
        self.greeting = self.config.get("greeting", "您好，请问有什么可以帮您？")
        self.silence_phrases = self.config.get("silence_phrases", [
            "嗯，好的，请讲",
            "我在听",
            "嗯嗯",
            "请说"
        ])
        self.end_keywords = self.config.get("end_keywords", [
            "再见", "挂了", "谢谢", "再见吧"
        ])
        self.max_turns = self.config.get("max_turns", 20)
        
        # 状态
        self.state = DialogState.IDLE
        self.current_turn = 0
        self.is_running = False
        
        # 回调
        self.on_state_change = None
        self.on_user_speak = None
        self.on_ai_reply = None
        self.on_dialog_end = None
        
        # 消息队列
        self.message_queue = queue.Queue()
        
    def dial_and_answer(self, phone_number: str) -> bool:
        """
        拨打电话并等待接听
        
        Args:
            phone_number: 电话号码
            
        Returns:
            是否成功
        """
        self._set_state(DialogState.DIALING)
        
        # 拨号
        print(f"正在拨号: {phone_number}")
        self.adb.dial(phone_number)
        
        # 等待接听
        self._set_state(DialogState.WAITING)
        print("等待对方接听...")
        
        if not self.adb.wait_for_answer(timeout=30):
            print("对方未接听")
            self._set_state(DialogState.IDLE)
            return False
        
        # 接听
        self.adb.answer_call()
        
        self._set_state(DialogState.CONNECTED)
        print("对方已接听")
        
        return True
    
    def start_conversation(self, greeting: str = None):
        """
        开始对话
        
        Args:
            greeting: 开场白
        """
        self._set_state(DialogState.CONVERSING)
        self.is_running = True
        self.current_turn = 0
        
        text = greeting or self.greeting
        self._play_and_wait(text)
        
        # 启动对话循环
        self._conversation_loop()
    
    def _conversation_loop(self):
        """对话循环"""
        from vad import AudioBuffer
        from asr_client import StreamASRHandler
        
        # 初始化组件
        audio_buffer = AudioBuffer()
        asr_handler = StreamASRHandler(self.asr, self.vad, audio_buffer)
        
        # 设置VAD回调
        def on_speech_start():
            audio_buffer.start_recording()
        
        def on_speech_end():
            if audio_buffer.get_duration() > 0.3:
                try:
                    audio = audio_buffer.stop_recording()
                    result = self.asr.recognize(audio, timeout=5)
                    if result:
                        self._handle_user_input(result)
                except Exception as e:
                    print(f"识别错误: {e}")
        
        self.vad.on_speech_start = on_speech_start
        self.vad.on_speech_end = on_speech_end
        
        # 开始音频采集
        self.audio.start()
        
        # 循环处理
        while self.is_running and self.current_turn < self.max_turns:
            # 获取音频
            audio_chunk = self.audio.get_audio(timeout=1.0)
            if audio_chunk:
                # VAD处理
                asr_handler.process_audio(audio_chunk)
            
            # 检查是否结束
            if self.state == DialogState.ENDING:
                break
        
        # 结束对话
        self._end_conversation()
    
    def _handle_user_input(self, text: str):
        """
        处理用户输入
        
        Args:
            text: 用户说的文本
        """
        print(f"用户: {text}")
        
        if self.on_user_speak:
            self.on_user_speak(text)
        
        # 检查结束关键词
        for keyword in self.end_keywords:
            if keyword in text:
                print("检测到结束关键词，对话结束")
                self._set_state(DialogState.ENDING)
                return
        
        # 增加轮次
        self.current_turn += 1
        
        # TODO: 调用大模型生成回复
        # 这里暂时用占位回复
        ai_reply = self._generate_reply(text)
        
        # 播放回复
        self._play_and_wait(ai_reply)
        
        if self.on_ai_reply:
            self.on_ai_reply(ai_reply)
    
    def _generate_reply(self, user_text: str) -> str:
        """
        生成回复 (TODO: 接入大模型)
        
        Args:
            user_text: 用户说的
            
        Returns:
            AI回复
        """
        # 占位实现
        replies = [
            "好的，我明白了",
            "嗯，我在听",
            "让我想想",
            "明白您的意思了"
        ]
        
        import random
        return random.choice(replies)
    
    def _play_and_wait(self, text: str):
        """
        播放TTS并等待完成
        
        Args:
            text: 要播放的文本
        """
        try:
            # 合成语音
            audio = self.tts.synthesize(text)
            
            # 播放
            self.audio.player.play_tts_stream(audio)
            
            # 等待播放完成 (简单等待)
            time.sleep(len(text) / 5)  # 估算
        except Exception as e:
            print(f"播放失败: {e}")
    
    def _end_conversation(self):
        """结束对话"""
        self.is_running = False
        
        # 播放结束语
        self._play_and_wait("好的，再见")
        
        # 挂断
        self.adb.hangup()
        
        # 停止音频采集
        self.audio.stop()
        
        self._set_state(DialogState.FINISHED)
        
        if self.on_dialog_end:
            self.on_dialog_end()
        
        print("对话结束")
    
    def stop(self):
        """停止对话"""
        self.is_running = False
        self._set_state(DialogState.ENDING)
    
    def _set_state(self, state: DialogState):
        """设置状态"""
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)
    
    def get_state(self) -> DialogState:
        """获取当前状态"""
        return self.state


class MultiCallManager:
    """多路通话管理器"""
    
    def __init__(self):
        self.devices: Dict[str, DialogManager] = {}
    
    def register_device(self, device_id: str, manager: DialogManager):
        """注册设备"""
        self.devices[device_id] = manager
    
    def dial_all(self, calls: list) -> Dict[str, bool]:
        """
        同时拨打多个电话
        
        Args:
            calls: [(device_id, phone_number), ...]
            
        Returns:
            {device_id: success}
        """
        results = {}
        threads = []
        
        def dial(device_id, phone_number):
            manager = self.devices.get(device_id)
            if manager:
                results[device_id] = manager.dial_and_answer(phone_number)
        
        for device_id, phone_number in calls:
            t = threading.Thread(target=dial, args=(device_id, phone_number))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
        
        return results
    
    def start_all_conversations(self, greeting: str = None):
        """开始所有对话"""
        for manager in self.devices.values():
            manager.start_conversation(greeting)
    
    def stop_all(self):
        """停止所有对话"""
        for manager in self.devices.values():
            manager.stop()


def create_dialog_manager(config: dict) -> DialogManager:
    """
    创建对话管理器
    
    Args:
        config: 配置
        
    Returns:
        DialogManager实例
    """
    # 这里需要传入实际的组件
    # 实际使用时由外部组装
    return DialogManager(None, None, None, None, None, config)


if __name__ == "__main__":
    # 测试
    print("对话管理器测试")
    
    # 测试状态
    dm = DialogManager(None, None, None, None, None)
    print(f"初始状态: {dm.get_state().value}")