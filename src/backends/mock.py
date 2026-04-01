"""Mock backend for development and testing without real hardware."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .base import TelephonyBackend, CallState

logger = logging.getLogger(__name__)


class MockBackend(TelephonyBackend):
    """Simulates a phone call without any hardware."""

    def __init__(self):
        self._state = CallState.IDLE
        self._healthy = True

    async def initialize(self) -> None:
        logger.info("Mock backend initialized")

    async def dial(self, number: str) -> bool:
        logger.info("[Mock] Dialing %s", number)
        self._state = CallState.DIALING
        await asyncio.sleep(1)
        self._state = CallState.ACTIVE
        logger.info("[Mock] Call connected to %s", number)
        return True

    async def answer(self) -> bool:
        self._state = CallState.ACTIVE
        return True

    async def hangup(self) -> bool:
        self._state = CallState.IDLE
        logger.info("[Mock] Call hung up")
        return True

    async def read_audio(self, num_samples: int) -> Optional[bytes]:
        await asyncio.sleep(0.02)
        return b"\x80" * num_samples  # mulaw silence

    async def write_audio(self, data: bytes) -> None:
        pass

    async def get_state(self) -> CallState:
        return self._state

    def is_healthy(self) -> bool:
        return self._healthy

    def device_info(self) -> dict:
        return {
            "type": "MockBackend",
            "healthy": True,
            "state": self._state.name,
        }
