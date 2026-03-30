"""
Phone Skill - 电话 Skill 主程序（v2）

对齐 @openclaw/voice-call：
- 上行 task：持续读音频 → VAD → UtteranceSegmenter → finalized 后入队
- 下行 task：从队列取 user_text → Gateway（带思考话术兜底）→ TTS 分帧下行
- barge-in：上行 task 检测 speech_just_started 时清空播放队列
- 异常保护：try/finally 保证清理 scrcpy/ffmpeg/player/hangup
- 通话时长限制、管道健康检测、持续无输出道歉循环
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional

from .phone_controller import PhoneController, CallState
from .audio_capture import AudioCapture
from .audio_player import AudioPlayer
from .static_audio_cache import StaticAudioCache
from .call_record import CallRecord, CallRecordData
from .http_api import APIServer as HTTPServer
from . import config
from .config import AUDIO_CONFIG, CALL_CONFIG

logger = logging.getLogger(__name__)

_MIN_UTTERANCE_BYTES = 3200
_EMPTY_READ_THRESHOLD = 50  # 连续空读次数，超过则检查管道健康


def _time_of_day_key() -> str:
    """6-12 morning, 12-18 afternoon, else evening."""
    h = datetime.now().hour
    if 6 <= h < 12:
        return "morning"
    elif 12 <= h < 18:
        return "afternoon"
    return "evening"


def _build_static_audio_mapping() -> Dict[str, str]:
    """构建所有固定话术的 {cache_key: text} 映射。"""
    agent_name = CALL_CONFIG.get("agent_name", "小甜甜")
    mapping: Dict[str, str] = {}

    for period, tpl in CALL_CONFIG.get("welcome_templates", {}).items():
        mapping[f"welcome_{period}"] = tpl.format(agent_name=agent_name)

    for i, phrase in enumerate(CALL_CONFIG.get("thinking_phrases", [])):
        mapping[f"thinking_{i}"] = phrase

    apology = CALL_CONFIG.get("apology_message", "")
    if apology:
        mapping["apology"] = apology

    farewell = CALL_CONFIG.get("farewell_message", "")
    if farewell:
        mapping["farewell"] = farewell

    for i, phrase in enumerate(CALL_CONFIG.get("filler_phrases", [])):
        mapping[f"filler_{i}"] = phrase

    return mapping


class PhoneSkill:
    """整合外呼、采集、句末 ASR、OpenClaw 回复、TTS 与打断。"""

    def __init__(self):
        self.phone_controller = PhoneController()
        self.audio_capture = AudioCapture()
        self.audio_player = AudioPlayer()

        from .ai_pipeline import VADManager, ASRManager, TTSManager

        self.vad = VADManager()
        self.asr = ASRManager()
        self.tts = TTSManager()

        self.static_cache = StaticAudioCache(tts_manager=self.tts)
        self.call_record = CallRecord()

        self.http_server = HTTPServer(
            host=CALL_CONFIG.get("http_host", "0.0.0.0"),
            port=CALL_CONFIG.get("http_port", 8080),
        )
        self.http_server.register_call_record(self.call_record)

        self._running = False
        self._current_phone_number: Optional[str] = None
        self._call_start_time: Optional[float] = None
        self._call_type = "outbound"
        self._transcript_lines: List[str] = []
        self._agent_speaking = False
        self._last_meaningful_output_ts: float = 0.0

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        logger.info("Initializing Phone Skill...")
        self.vad.load_model()
        self.asr.load_model()

        mapping = _build_static_audio_mapping()
        await self.static_cache.ensure_all(mapping)

        self.http_server.start()
        logger.info("Phone Skill initialized (%d static audio cached)", len(mapping))

    # ------------------------------------------------------------------
    # 播放辅助
    # ------------------------------------------------------------------

    def _play_static(self, key: str) -> bool:
        """播放预生成 PCM（零延迟）。返回是否成功。"""
        pcm = self.static_cache.get(key)
        if not pcm:
            logger.warning("Static audio not found: %s", key)
            return False
        frame_bytes = self._tts_frame_bytes()
        for i in range(0, len(pcm), frame_bytes):
            if not self._running:
                return False
            self.audio_player.play(pcm[i : i + frame_bytes])
        return True

    def _tts_frame_bytes(self) -> int:
        frame_ms = float(CALL_CONFIG.get("tts_frame_ms", 20))
        bps = AUDIO_CONFIG["channels"] * 2
        sr = AUDIO_CONFIG["sample_rate"]
        return max(int(sr * bps * frame_ms / 1000.0), 2)

    async def _play_text_chunked(self, text: str) -> None:
        """TTS 合成并按小块入队播放。"""
        frame_bytes = self._tts_frame_bytes()
        self._agent_speaking = True
        try:
            async for chunk in self.tts.synthesize(text):
                for i in range(0, len(chunk), frame_bytes):
                    if not self._agent_speaking:
                        return
                    self.audio_player.play(chunk[i : i + frame_bytes])
                    await asyncio.sleep(0)
        finally:
            self._agent_speaking = False

    # ------------------------------------------------------------------
    # OpenClaw 调用
    # ------------------------------------------------------------------

    def _fetch_agent_reply(self, user_message: str) -> str:
        from .openclaw_bridge import mock_reply, request_agent_text

        if os.environ.get("PHONE_SKILL_USE_MOCK_ONLY", "").strip() == "1":
            return mock_reply(user_message)

        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
        if not token:
            logger.info("未设置 OPENCLAW_GATEWAY_TOKEN，使用占位回复")
            return mock_reply(user_message)

        session_user = self._current_phone_number or ""
        timeout = int(CALL_CONFIG.get("gateway_timeout_s", 10))
        text = request_agent_text(
            user_message,
            transcript_lines=self._transcript_lines[-24:],
            session_user=session_user,
            timeout=timeout,
        )
        if text:
            return text
        fallback = CALL_CONFIG.get("gateway_fallback_reply", "")
        return fallback if fallback else mock_reply(user_message)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def phone_call(self, phone_number: str) -> AsyncGenerator[dict, None]:
        from .voice_utterance import UtteranceSegmenter, UtteranceSegmenterConfig

        self._current_phone_number = phone_number
        self._call_start_time = time.time()
        self._call_type = "outbound"
        self._transcript_lines = []
        self._running = True
        self._agent_speaking = False
        self._last_meaningful_output_ts = 0.0

        event_queue: asyncio.Queue[dict] = asyncio.Queue()
        utterance_queue: asyncio.Queue[str] = asyncio.Queue()

        logger.info("Starting outbound call to %s", phone_number)
        yield {"event": "status", "status": "dialing", "phone": phone_number}

        # --- 启动音频管道 ---
        try:
            self.audio_capture.start_capture()
        except Exception as e:
            logger.error("Failed to start audio capture: %s", e)
            yield {"event": "status", "status": "failed", "reason": "capture_failed"}
            return

        try:
            self.audio_player.start()
        except Exception as e:
            logger.error("Failed to start audio player: %s", e)
            self.audio_capture.stop_capture()
            yield {"event": "status", "status": "failed", "reason": "audio_player_failed"}
            return

        # --- 拨号 ---
        if not self.phone_controller.dial(phone_number):
            self._cleanup()
            yield {"event": "status", "status": "failed", "reason": "dial_failed"}
            return

        yield {"event": "status", "status": "connecting"}

        if not self.phone_controller.wait_for_state(CallState.OFFHOOK, timeout=60):
            self._cleanup()
            yield {"event": "status", "status": "no_answer"}
            return

        yield {"event": "status", "status": "call_started"}

        # --- 播放问候语（预生成 PCM） ---
        period_key = _time_of_day_key()
        welcome_cache_key = f"welcome_{period_key}"
        welcome_text = CALL_CONFIG.get("welcome_templates", {}).get(
            period_key, "您好！"
        ).format(agent_name=CALL_CONFIG.get("agent_name", "小甜甜"))

        self._play_static(welcome_cache_key)
        self._last_meaningful_output_ts = time.time()
        yield {"event": "agent_responding", "text": welcome_text}
        self._transcript_lines.append(f"助手: {welcome_text}")

        # --- segmenter ---
        seg_cfg = UtteranceSegmenterConfig(
            sample_rate=AUDIO_CONFIG["sample_rate"],
            channels=AUDIO_CONFIG["channels"],
            end_silence_ms=float(CALL_CONFIG.get("utterance_end_silence_ms", 750.0)),
            min_speech_ms=float(CALL_CONFIG.get("utterance_min_speech_ms", 250.0)),
            max_utterance_ms=float(CALL_CONFIG.get("max_audio_duration_ms", 15000)),
        )
        segmenter = UtteranceSegmenter(seg_cfg)

        # --- 并发 task ---
        uplink_task = asyncio.create_task(
            self._uplink_loop(segmenter, event_queue, utterance_queue)
        )
        downlink_task = asyncio.create_task(
            self._downlink_loop(event_queue, utterance_queue)
        )

        try:
            while self._running:
                # 从 event_queue 收集事件 yield 给调用者
                try:
                    ev = event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.02)
                    continue

                yield ev

                if ev.get("status") in ("ended", "failed", "capture_lost", "max_duration_reached"):
                    break
        except Exception as e:
            logger.error("phone_call loop error: %s", e)
            event_queue.put_nowait({"event": "status", "status": "error", "reason": str(e)})
        finally:
            self._running = False
            uplink_task.cancel()
            downlink_task.cancel()
            for t in (uplink_task, downlink_task):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            self._cleanup()

            duration = int(time.time() - (self._call_start_time or time.time()))
            yield {
                "event": "call_summary",
                "phone": phone_number,
                "duration": duration,
                "turns": len(self._transcript_lines),
            }

            # best-effort 通知 Gateway
            try:
                from .openclaw_bridge import notify_call_ended
                await asyncio.to_thread(
                    notify_call_ended, phone_number, duration, self._transcript_lines[-24:]
                )
            except Exception:
                pass

            yield {"event": "status", "status": "ended"}

    # ------------------------------------------------------------------
    # 上行 task：读音频 → VAD → segmenter → barge-in / ASR → 入队
    # ------------------------------------------------------------------

    async def _uplink_loop(
        self,
        segmenter,
        event_queue: asyncio.Queue,
        utterance_queue: asyncio.Queue,
    ) -> None:
        max_duration = int(CALL_CONFIG.get("max_call_duration", 600))
        empty_count = 0

        try:
            while self._running:
                # 通话时长检查
                elapsed = time.time() - (self._call_start_time or time.time())
                if elapsed >= max_duration:
                    logger.info("Max call duration reached (%ds)", max_duration)
                    self._play_static("farewell")
                    self.phone_controller.hangup()
                    event_queue.put_nowait({"event": "status", "status": "max_duration_reached"})
                    return

                # 对方挂断检查
                if self.phone_controller.get_call_state() == CallState.IDLE:
                    logger.info("Remote party hung up")
                    event_queue.put_nowait({"event": "status", "status": "ended"})
                    return

                # 读上行音频（非阻塞线程）
                audio_chunk = await asyncio.to_thread(self.audio_capture.read)
                if not audio_chunk:
                    empty_count += 1
                    if empty_count >= _EMPTY_READ_THRESHOLD and not self.audio_capture.is_healthy():
                        logger.error("Audio capture pipe broken")
                        event_queue.put_nowait({"event": "status", "status": "capture_lost"})
                        return
                    await asyncio.sleep(0.02)
                    continue

                empty_count = 0

                is_speech, _ts = self.vad.detect_speech(audio_chunk)
                finalized, speech_started = segmenter.feed(audio_chunk, is_speech)

                # barge-in
                if speech_started and self._agent_speaking:
                    self._agent_speaking = False
                    self.audio_player.barge_in()
                    event_queue.put_nowait({"event": "status", "status": "barge_in"})
                    logger.info("Barge-in: user speech during agent TTS")

                # 句末 → ASR → 入队
                if finalized and len(finalized) >= _MIN_UTTERANCE_BYTES:
                    user_text = await asyncio.to_thread(self.asr.transcribe, finalized)
                    user_text = (user_text or "").strip()
                    if user_text:
                        logger.info("User (final): %s", user_text)
                        event_queue.put_nowait(
                            {"event": "user_speaking", "text": user_text, "final": True}
                        )
                        self._transcript_lines.append(f"用户: {user_text}")
                        utterance_queue.put_nowait(user_text)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Uplink loop error: %s", e)
            event_queue.put_nowait({"event": "status", "status": "error", "reason": str(e)})

    # ------------------------------------------------------------------
    # 下行 task：从队列取文本 → 思考话术 → Gateway → TTS 播放 → 道歉兜底
    # ------------------------------------------------------------------

    async def _downlink_loop(
        self,
        event_queue: asyncio.Queue,
        utterance_queue: asyncio.Queue,
    ) -> None:
        thinking_delay = float(CALL_CONFIG.get("thinking_delay_ms", 3000)) / 1000.0
        apology_interval = float(CALL_CONFIG.get("apology_interval_s", 10))
        thinking_keys = [
            k for k in (f"thinking_{i}" for i in range(20))
            if self.static_cache.has(k)
        ]

        try:
            while self._running:
                # 道歉兜底检查（在空闲等待中持续运行）
                now = time.time()
                if (
                    self._last_meaningful_output_ts > 0
                    and not self._agent_speaking
                    and (now - self._last_meaningful_output_ts) >= apology_interval
                ):
                    self._play_static("apology")
                    self._last_meaningful_output_ts = now
                    event_queue.put_nowait({"event": "status", "status": "apology_played"})

                # 非阻塞取用户文本
                try:
                    user_text = utterance_queue.get_nowait()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.1)
                    continue

                # 并发：Gateway 请求 + 思考话术计时
                gateway_done = asyncio.Event()
                agent_reply_holder: List[Optional[str]] = [None]

                async def gateway_call():
                    reply = await asyncio.to_thread(self._fetch_agent_reply, user_text)
                    agent_reply_holder[0] = reply
                    gateway_done.set()

                async def thinking_timer():
                    await asyncio.sleep(thinking_delay)
                    if not gateway_done.is_set() and thinking_keys:
                        key = random.choice(thinking_keys)
                        if not self._agent_speaking:
                            self._play_static(key)
                            event_queue.put_nowait({"event": "status", "status": "thinking_played"})

                gw_task = asyncio.create_task(gateway_call())
                th_task = asyncio.create_task(thinking_timer())

                try:
                    await gw_task
                finally:
                    th_task.cancel()
                    try:
                        await th_task
                    except asyncio.CancelledError:
                        pass

                agent_reply = agent_reply_holder[0]
                if agent_reply:
                    event_queue.put_nowait({"event": "agent_text", "text": agent_reply})
                    await self._play_text_chunked(agent_reply)
                    event_queue.put_nowait({"event": "agent_responding", "text": agent_reply})
                    self._transcript_lines.append(f"助手: {agent_reply}")
                    self._last_meaningful_output_ts = time.time()
                    self._save_call_record(user_text, agent_reply)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Downlink loop error: %s", e)
            event_queue.put_nowait({"event": "status", "status": "error", "reason": str(e)})

    # ------------------------------------------------------------------
    # 通话记录
    # ------------------------------------------------------------------

    def _save_call_record(self, user_text: str, agent_response: str) -> None:
        if not self._current_phone_number:
            return
        try:
            record = CallRecordData(
                phone_number=self._current_phone_number,
                call_time=datetime.fromtimestamp(self._call_start_time or time.time()),
                duration=int(time.time() - (self._call_start_time or time.time())),
                call_type=self._call_type,
                user_text=user_text,
                agent_response=agent_response,
            )
            self.call_record.save(record)
        except Exception as e:
            logger.error("Failed to save call record: %s", e)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        """统一资源清理：停采集、停播放、挂断电话。"""
        self._running = False
        self._agent_speaking = False
        try:
            self.audio_capture.stop_capture()
        except Exception:
            pass
        try:
            self.audio_player.barge_in()
            if self.audio_player.is_running():
                self.audio_player.stop()
        except Exception:
            pass
        try:
            if self.phone_controller.get_call_state() != CallState.IDLE:
                self.phone_controller.hangup()
        except Exception:
            pass

    async def shutdown(self) -> None:
        logger.info("Shutting down Phone Skill...")
        self._cleanup()
        self.http_server.stop()
        self.call_record.close()
        logger.info("Phone Skill stopped")


# ------------------------------------------------------------------
# Tool factory / CLI
# ------------------------------------------------------------------

def create_phone_call_tool(phone_skill: PhoneSkill):
    async def phone_call(phone_number: str):
        async for ev in phone_skill.phone_call(phone_number):
            yield ev
    return phone_call


async def main() -> None:
    config.configure_logging()
    parser = argparse.ArgumentParser(description="Phone Skill")
    parser.add_argument("command", choices=["call", "test"], help="Command")
    parser.add_argument("args", nargs="*", help="Arguments")

    args = parser.parse_args()

    if args.command == "call":
        phone_number = args.args[0] if args.args else "13800138000"
        skill = PhoneSkill()
        await skill.initialize()
        try:
            async for event in skill.phone_call(phone_number):
                print(json.dumps(event, ensure_ascii=False))
        finally:
            await skill.shutdown()

    elif args.command == "test":
        print("Testing Phone Skill components...")
        skill = PhoneSkill()
        await skill.initialize()
        await skill.shutdown()
        print("Test completed")


if __name__ == "__main__":
    asyncio.run(main())
