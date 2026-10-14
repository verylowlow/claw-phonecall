import asyncio
import json
import logging
import websockets
from typing import Any, Optional, Callable, Awaitable

from .protocol import (
    build_start_message,
    build_media_message,
    build_stop_message,
    parse_message,
)

logger = logging.getLogger(__name__)

_CONNECT_ATTEMPTS = 5
_CONNECT_BASE_DELAY_S = 1.0


class MediaStreamClient:
    def __init__(
        self,
        stream_url: str,
        stream_sid: str,
        call_sid: str,
        account_sid: str,
        token: Optional[str] = None,
    ) -> None:
        self._stream_url = stream_url
        self._stream_sid = stream_sid
        self._call_sid = call_sid
        self._account_sid = account_sid
        self._token = token
        self._ws: Optional[Any] = None

    @property
    def is_connected(self) -> bool:
        ws = self._ws
        if ws is None:
            return False
        close_code = getattr(ws, "close_code", None)
        return close_code is None

    async def connect(self) -> None:
        last_exc: Optional[BaseException] = None
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        for attempt in range(1, _CONNECT_ATTEMPTS + 1):
            try:
                self._ws = await websockets.connect(
                    self._stream_url,
                    extra_headers=headers or None,
                )
                start = build_start_message(
                    stream_sid=self._stream_sid,
                    call_sid=self._call_sid,
                    account_sid=self._account_sid,
                    token=self._token,
                )
                await self._ws.send(start)
                logger.info(
                    "Media stream connected to %s (attempt %s/%s)",
                    self._stream_url,
                    attempt,
                    _CONNECT_ATTEMPTS,
                )
                return
            except Exception as e:
                last_exc = e
                logger.warning(
                    "Media stream connect failed (%s/%s): %s",
                    attempt,
                    _CONNECT_ATTEMPTS,
                    e,
                    exc_info=logger.isEnabledFor(logging.DEBUG),
                )
                self._ws = None
                if attempt < _CONNECT_ATTEMPTS:
                    delay = _CONNECT_BASE_DELAY_S * attempt
                    logger.info("Retrying media stream connect in %.1fs", delay)
                    await asyncio.sleep(delay)

        logger.error(
            "Giving up media stream connection after %s attempts",
            _CONNECT_ATTEMPTS,
        )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Media stream connect failed with no exception")

    async def send_audio(
        self,
        payload_b64: str,
        seq_num: int,
        chunk_num: int,
        timestamp_ms: int,
    ) -> None:
        if not self.is_connected or self._ws is None:
            logger.debug("send_audio skipped: not connected")
            return
        msg = build_media_message(
            self._stream_sid,
            payload_b64=payload_b64,
            seq_num=seq_num,
            chunk_num=chunk_num,
            timestamp_ms=timestamp_ms,
        )
        await self._ws.send(msg)

    async def send_stop(self) -> None:
        if not self.is_connected or self._ws is None:
            logger.debug("send_stop skipped: not connected")
            return
        await self._ws.send(build_stop_message(self._stream_sid))

    async def run(
        self,
        on_audio: Callable[[str], Awaitable[None]],
        on_clear: Callable[[], Awaitable[None]],
        on_mark: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        if self._ws is None:
            logger.warning("MediaStreamClient.run called without an active connection")
            return

        while self.is_connected:
            try:
                raw = await self._ws.recv()
            except websockets.exceptions.ConnectionClosed as e:
                logger.info(
                    "Media stream WebSocket closed (code=%s reason=%s); exiting receive loop",
                    e.code,
                    e.reason,
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error receiving media stream frame")
                break

            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except UnicodeDecodeError:
                    logger.warning("Ignoring non-UTF-8 binary media stream frame")
                    continue

            try:
                msg = parse_message(raw)
            except json.JSONDecodeError:
                logger.warning("Ignoring non-JSON media stream frame: %s", raw[:200])
                continue

            event = msg.get("event")
            if event == "media":
                media = msg.get("media") or {}
                payload = media.get("payload")
                if isinstance(payload, str):
                    await on_audio(payload)
                else:
                    logger.debug("media event without payload string: %s", msg)
            elif event == "clear":
                await on_clear()
            elif event == "mark":
                mark_name: Optional[str] = None
                mark = msg.get("mark")
                if isinstance(mark, dict):
                    mark_name = mark.get("name")
                if mark_name is None:
                    mark_name = msg.get("name") if isinstance(msg.get("name"), str) else None
                if on_mark is not None and mark_name is not None:
                    await on_mark(mark_name)
                elif on_mark is None:
                    logger.debug("mark event ignored (no callback): %s", msg)

    async def close(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                logger.debug("Error closing media stream WebSocket", exc_info=True)
