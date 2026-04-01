"""
AgentCallCenter Bridge Manager — orchestrates the call flow:

1. Receive call request from voice-call (via Twilio REST API compat)
2. Dial the number on the hardware backend
3. Send status webhooks back to voice-call
4. Fetch TwiML to get the Stream URL
5. Open WebSocket to voice-call's /voice/stream
6. Bridge audio bidirectionally between hardware and WebSocket
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

from src.config import BRIDGE_CONFIG, TWILIO_COMPAT_CONFIG, RECORDING_CONFIG
from src.twilio_compat.webhook import send_status_callback, fetch_twiml
from src.twilio_compat.twiml_parser import parse_twiml
from src.media_stream.ws_client import MediaStreamClient
from src.media_stream.codec import encode_payload, decode_payload
from src.recording.recorder import CallRecorder

logger = logging.getLogger(__name__)

_backend = None
_active_sessions: Dict[str, "CallSession"] = {}


class CallSession:
    """Manages a single bridged call."""

    def __init__(
        self,
        call_sid: str,
        account_sid: str,
        to: str,
        from_number: str,
        twiml_url: str,
        status_callback: Optional[str] = None,
    ):
        self.call_sid = call_sid
        self.account_sid = account_sid
        self.to = to
        self.from_number = from_number
        self.twiml_url = twiml_url
        self.status_callback = status_callback
        self.stream_sid = "MZ" + uuid.uuid4().hex
        self.start_time = time.time()
        self.status = "initiated"

        self._ws_client: Optional[MediaStreamClient] = None
        self._recorder: Optional[CallRecorder] = None
        self._bridge_task: Optional[asyncio.Task] = None
        self._seq_num = 2  # 1 is used by start message
        self._chunk_num = 0

    async def run(self) -> None:
        try:
            await self._notify_status("initiated")
            await self._notify_status("ringing")

            if not await self._dial():
                await self._notify_status("failed")
                return

            await self._notify_status("in-progress")

            twiml_xml = await fetch_twiml(
                self.twiml_url, self.call_sid, self.from_number, self.to
            )
            if not twiml_xml:
                logger.error("Failed to fetch TwiML for call %s", self.call_sid)
                await self._notify_status("failed")
                return

            parsed = parse_twiml(twiml_xml)
            stream_url = parsed.get("stream_url")
            token = parsed.get("parameters", {}).get("token")

            if not stream_url:
                logger.error("No <Stream> URL in TwiML for call %s", self.call_sid)
                await self._notify_status("failed")
                return

            if RECORDING_CONFIG["enabled"]:
                self._recorder = CallRecorder(
                    self.call_sid, self.to, RECORDING_CONFIG["directory"]
                )

            from src.db.models import insert_call
            insert_call(
                call_sid=self.call_sid,
                phone_number=self.to,
                direction="outbound",
                backend_type=BRIDGE_CONFIG["backend_type"],
                stream_sid=self.stream_sid,
                account_sid=self.account_sid,
            )

            logger.info("Connecting media stream to %s for call %s", stream_url, self.call_sid)

            self._ws_client = MediaStreamClient(
                stream_url=stream_url,
                stream_sid=self.stream_sid,
                call_sid=self.call_sid,
                account_sid=self.account_sid,
                token=token,
            )
            await self._ws_client.connect()

            uplink_task = asyncio.create_task(self._uplink_loop())
            downlink_task = asyncio.create_task(
                self._ws_client.run(
                    on_audio=self._on_downlink_audio,
                    on_clear=self._on_clear,
                )
            )

            done, pending = await asyncio.wait(
                [uplink_task, downlink_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

        except Exception:
            logger.exception("CallSession error for %s", self.call_sid)
        finally:
            await self._cleanup()

    async def _dial(self) -> bool:
        if _backend is None:
            logger.warning("No backend configured, simulating dial success (mock)")
            return True
        try:
            return await _backend.dial(self.to)
        except Exception:
            logger.exception("Backend dial failed for %s", self.to)
            return False

    async def _uplink_loop(self) -> None:
        """Read audio from hardware backend, encode and send to voice-call."""
        timestamp_ms = 0
        chunk_ms = 20

        while True:
            if _backend is None:
                await asyncio.sleep(0.02)
                continue

            try:
                pcm = await _backend.read_audio(160)  # 160 samples = 20ms at 8kHz
                if not pcm:
                    await asyncio.sleep(0.01)
                    continue

                payload_b64 = encode_payload(pcm, src_rate=8000)
                self._seq_num += 1
                self._chunk_num += 1
                timestamp_ms += chunk_ms

                if self._recorder:
                    self._recorder.feed_uplink(pcm)

                if self._ws_client and self._ws_client.is_connected:
                    await self._ws_client.send_audio(
                        payload_b64, self._seq_num, self._chunk_num, timestamp_ms
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Uplink error")
                await asyncio.sleep(0.1)

    async def _on_downlink_audio(self, payload_b64: str) -> None:
        """Receive TTS audio from voice-call, decode and send to hardware."""
        try:
            pcm = decode_payload(payload_b64, dst_rate=8000)
            if self._recorder:
                self._recorder.feed_downlink(pcm)
            if _backend is not None:
                await _backend.write_audio(pcm)
        except Exception:
            logger.exception("Downlink audio error")

    async def _on_clear(self) -> None:
        """Barge-in: voice-call wants to clear the TTS queue."""
        logger.info("Barge-in clear received for call %s", self.call_sid)
        if _backend and hasattr(_backend, "clear_playback"):
            try:
                await _backend.clear_playback()
            except Exception:
                pass

    async def _notify_status(self, status: str) -> None:
        self.status = status
        from src.twilio_compat.rest_api import update_call_status
        update_call_status(self.call_sid, status)

        if self.status_callback:
            await send_status_callback(
                self.status_callback,
                self.call_sid,
                status,
                self.from_number,
                self.to,
                AccountSid=self.account_sid,
            )

    async def _cleanup(self) -> None:
        if self._ws_client:
            try:
                await self._ws_client.send_stop()
            except Exception:
                pass
            try:
                await self._ws_client.close()
            except Exception:
                pass
            self._ws_client = None

        if _backend:
            try:
                await _backend.hangup()
            except Exception:
                pass

        recording_path = None
        if self._recorder:
            try:
                recording_path = self._recorder.stop()
            except Exception:
                logger.exception("Failed to save recording")

        duration = int(time.time() - self.start_time)

        try:
            from src.db.models import complete_call
            complete_call(self.call_sid, duration, recording_path)
        except Exception:
            logger.exception("Failed to update call record in DB")

        await self._notify_status("completed")
        _active_sessions.pop(self.call_sid, None)
        logger.info("Call %s completed (duration=%ds, recording=%s)",
                     self.call_sid, duration, recording_path)


async def initiate_call(
    call_sid: str,
    account_sid: str,
    to: str,
    from_number: str,
    url: str,
    status_callback: Optional[str] = None,
    status_callback_event: Optional[str] = None,
    **kwargs: Any,
) -> None:
    session = CallSession(
        call_sid=call_sid,
        account_sid=account_sid,
        to=to,
        from_number=from_number,
        twiml_url=url,
        status_callback=status_callback,
    )
    _active_sessions[call_sid] = session
    asyncio.create_task(session.run())


def get_session(call_sid: str) -> Optional[CallSession]:
    return _active_sessions.get(call_sid)


def get_all_sessions() -> Dict[str, CallSession]:
    return dict(_active_sessions)


def set_backend(backend: Any) -> None:
    global _backend
    _backend = backend
    logger.info("Bridge backend set: %s", type(backend).__name__)


async def init_db() -> None:
    from src.db.models import init_db as _init_db
    await asyncio.to_thread(_init_db)


async def start_device_monitoring() -> None:
    backend_type = BRIDGE_CONFIG["backend_type"]
    logger.info("Initializing backend: %s", backend_type)

    import os

    if backend_type == "sim800c":
        from src.backends.sim800c import SIM800CBackend
        at_port = os.getenv("SIMCOM_AT_PORT", "COM3")
        audio_port = os.getenv("SIMCOM_AUDIO_PORT", "") or None
        baud = int(os.getenv("SIMCOM_BAUD_RATE", "115200"))
        backend = SIM800CBackend(at_port, audio_port, baud)
        await backend.initialize()
        set_backend(backend)
    elif backend_type == "sim7600":
        from src.backends.sim7600 import SIM7600Backend
        at_port = os.getenv("SIMCOM_AT_PORT", "COM5")
        audio_port = os.getenv("SIMCOM_AUDIO_PORT", "COM6")
        baud = int(os.getenv("SIMCOM_BAUD_RATE", "115200"))
        backend = SIM7600Backend(at_port, audio_port, baud)
        await backend.initialize()
        set_backend(backend)
    elif backend_type == "usb_modem":
        from src.backends.usb_modem import USBModemBackend
        port = os.getenv("MODEM_PORT", "COM3")
        baud = int(os.getenv("MODEM_BAUD_RATE", "115200"))
        backend = USBModemBackend(port, baud)
        await backend.initialize()
        set_backend(backend)
    elif backend_type == "android":
        from src.backends.android import AndroidBackend
        device_id = os.getenv("ANDROID_DEVICE_ID")
        backend = AndroidBackend(device_id)
        await backend.initialize()
        set_backend(backend)
    elif backend_type == "mock":
        from src.backends.mock import MockBackend
        backend = MockBackend()
        await backend.initialize()
        set_backend(backend)
    else:
        logger.warning("Unknown backend type: %s, running without hardware", backend_type)

    from src.db.models import upsert_device
    if _backend:
        info = _backend.device_info()
        await asyncio.to_thread(
            upsert_device,
            info.get("type", backend_type),
            info.get("device_id", info.get("port", "default")),
            "online" if _backend.is_healthy() else "offline",
        )


async def shutdown() -> None:
    for sid, session in list(_active_sessions.items()):
        await session._cleanup()
    _active_sessions.clear()
    logger.info("Bridge manager shutdown complete")
