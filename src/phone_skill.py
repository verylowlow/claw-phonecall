"""
Phone Skill - 电话 Skill 主程序
作为 OpenClaw Tool 长期运行的事件流程序
"""

import asyncio
import argparse
import logging
import sys
import json
import time
from datetime import datetime
from typing import Generator, Optional, Any

from .phone_controller import PhoneController, CallState
from .audio_capture import AudioCapture
from .audio_player import AudioPlayer
from .audio_buffer import AudioBuffer
from .filler_cache import FillerCache
from .call_record import CallRecord, CallRecordData
from .http_api import APIServer as HTTPServer
from .config import AUDIO_CONFIG, CALL_CONFIG

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PhoneSkill:
    """
    电话 Skill 主类
    整合所有组件，实现事件流架构
    """

    def __init__(self):
        """初始化电话 Skill"""
        # 核心组件
        self.phone_controller = PhoneController()
        self.audio_capture = AudioCapture()
        self.audio_player = AudioPlayer()

        # 音频处理
        self.audio_buffer = AudioBuffer(
            max_duration_ms=CALL_CONFIG.get("max_audio_duration_ms", 10000),
            sample_rate=AUDIO_CONFIG["sample_rate"],
            channels=AUDIO_CONFIG["channels"]
        )

        # VAD/ASR/TTS (从 ai_pipeline 导入)
        from .ai_pipeline import VADManager, ASRManager, TTSManager
        self.vad = VADManager()
        self.asr = ASRManager()
        self.tts = TTSManager()

        # 填充词缓存
        self.filler_cache = FillerCache(self.tts)

        # 通话记录
        self.call_record = CallRecord()

        # HTTP API
        self.http_server = HTTPServer(
            host=CALL_CONFIG.get("http_host", "0.0.0.0"),
            port=CALL_CONFIG.get("http_port", 8080)
        )
        self.http_server.register_call_record(self.call_record)

        # 状态
        self._running = False
        self._current_phone_number: Optional[str] = None
        self._call_start_time: Optional[float] = None
        self._call_type: str = "outbound"

    async def initialize(self) -> None:
        """初始化 (加载模型)"""
        logger.info("Initializing Phone Skill...")

        # 加载 AI 模型
        self.vad.load_model()
        self.asr.load_model()

        # 预加载填充词
        filler_phrases = CALL_CONFIG.get("filler_phrases", ["嗯", "好的", "我在听"])
        await self.filler_cache.preload(filler_phrases)

        # 启动 HTTP API
        self.http_server.start()

        logger.info("Phone Skill initialized")

    async def phone_call(self, phone_number: str) -> Generator[dict, None, None]:
        """
        发起外呼并进入通话循环
        这是一个生成器函数，通过 yield 返回事件

        Args:
            phone_number: 电话号码

        Yields:
            dict: 事件字典
        """
        self._current_phone_number = phone_number
        self._call_start_time = time.time()
        self._call_type = "outbound"

        logger.info(f"Starting outbound call to {phone_number}")

        # 1. 状态: dialing
        yield {"event": "status", "status": "dialing", "phone": phone_number}

        # 2. 拨号
        success = self.phone_controller.dial(phone_number)
        if not success:
            yield {"event": "status", "status": "failed", "reason": "dial_failed"}
            return

        # 3. 状态: connecting
        yield {"event": "status", "status": "connecting"}

        # 4. 等待对方接听
        if not self.phone_controller.wait_for_state(CallState.OFFHOOK, timeout=60):
            yield {"event": "status", "status": "no_answer"}
            return

        # 5. 状态: call_started
        yield {"event": "status", "status": "call_started"}

        # 6. 播放欢迎语
        welcome_msg = CALL_CONFIG.get("welcome_message", "您好，请问有什么可以帮您？")
        await self._play_text(welcome_msg)
        yield {"event": "agent_responding", "text": welcome_msg}

        # 7. 进入通话循环
        await self._call_loop()

        # 8. 通话结束
        self._save_call_record("", "")
        yield {"event": "status", "status": "ended"}

    async def _call_loop(self) -> Generator[dict, None, None]:
        """通话循环"""
        logger.info("Entering call loop")

        # 清空音频缓冲区
        self.audio_buffer.clear()

        while self._running and self.phone_controller.get_call_state() != CallState.IDLE:
            # 读取音频
            audio_chunk = self.audio_capture.read()
            if audio_chunk is None:
                await asyncio.sleep(0.05)
                continue

            # VAD 检测
            is_speech, speech_timestamps = self.vad.detect_speech(audio_chunk)

            # 累积音频
            self.audio_buffer.add(audio_chunk)

            # 检测到一句话结束 (静音段后有语音结束)
            if self._is_speech_ended(is_speech, speech_timestamps) and self.audio_buffer.has_content:
                # ASR 转写
                user_text = self.asr.transcribe(self.audio_buffer.get_audio())
                self.audio_buffer.clear()

                if user_text:
                    logger.info(f"User said: {user_text}")
                    yield {"event": "user_speaking", "text": user_text}

                    # 等待 Agent 回复 (通过 Tool 返回值)
                    # 这里需要通过某种方式接收 OpenClaw 的回复
                    # 暂时使用模拟回复，后续需要实现真正的交互
                    agent_response = await self._wait_for_agent_response()

                    if agent_response:
                        # TTS 播放
                        await self._play_text(agent_response)
                        yield {"event": "agent_responding", "text": agent_response}

                        # 保存通话记录
                        self._save_call_record(user_text, agent_response)

            await asyncio.sleep(0.05)

    def _is_speech_ended(self, is_speech: bool, speech_timestamps: list) -> bool:
        """
        判断一句话是否结束

        Args:
            is_speech: 是否有语音
            speech_timestamps: 语音时间戳列表

        Returns:
            bool: 是否结束
        """
        # 简单判断：如果之前有语音，现在没有语音，且时间戳显示有静音段
        if not is_speech and speech_timestamps:
            for ts in speech_timestamps:
                # 检查是否有较大的静音间隔
                if "end" in ts and "start" in ts:
                    duration = ts.get("end", 0) - ts.get("start", 0)
                    if duration > 500:  # 超过 500ms 的静音
                        return True
        return False

    async def _play_text(self, text: str) -> None:
        """
        播放文本 (TTS)

        Args:
            text: 要播放的文本
        """
        async for chunk in self.tts.synthesize(text):
            self.audio_player.play(chunk)

    async def _wait_for_agent_response(self) -> Optional[str]:
        """
        等待 Agent 回复
        这里需要实现与 OpenClaw 的交互

        Returns:
            Optional[str]: Agent 的回复
        """
        # TODO: 实现真正的 OpenClaw 交互
        # 暂时返回模拟回复
        await asyncio.sleep(0.5)
        return "您好，我理解了。请问还有什么可以帮您？"

    def _save_call_record(self, user_text: str, agent_response: str) -> None:
        """
        保存通话记录

        Args:
            user_text: 用户说的话
            agent_response: Agent 的回复
        """
        if not self._current_phone_number:
            return

        try:
            record = CallRecordData(
                phone_number=self._current_phone_number,
                call_time=datetime.fromtimestamp(self._call_start_time),
                duration=int(time.time() - self._call_start_time),
                call_type=self._call_type,
                user_text=user_text,
                agent_response=agent_response
            )
            self.call_record.save(record)
        except Exception as e:
            logger.error(f"Failed to save call record: {e}")

    async def shutdown(self) -> None:
        """关闭资源"""
        logger.info("Shutting down Phone Skill...")

        self._running = False
        self.audio_capture.stop()
        self.audio_player.stop()
        self.http_server.stop()
        self.call_record.close()

        logger.info("Phone Skill stopped")


def create_phone_call_tool(phone_skill: PhoneSkill):
    """
    创建 phone_call 工具函数

    Args:
        phone_skill: PhoneSkill 实例

    Returns:
        生成器函数
    """
    async def phone_call(phone_number: str) -> Generator[dict, None, None]:
        return phone_skill.phone_call(phone_number)

    return phone_call


# CLI 入口
async def main():
    """CLI 主函数"""
    parser = argparse.ArgumentParser(description="Phone Skill")
    parser.add_argument("command", choices=["call", "test"], help="Command")
    parser.add_argument("args", nargs="*", help="Arguments")

    args = parser.parse_args()

    if args.command == "call":
        phone_number = args.args[0] if args.args else "13800138000"

        skill = PhoneSkill()
        await skill.initialize()

        async for event in skill.phone_call(phone_number):
            print(json.dumps(event, ensure_ascii=False))

        await skill.shutdown()

    elif args.command == "test":
        print("Testing Phone Skill components...")
        skill = PhoneSkill()
        await skill.initialize()
        await skill.shutdown()
        print("Test completed")


if __name__ == "__main__":
    asyncio.run(main())