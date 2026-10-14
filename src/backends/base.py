"""Abstract base class for telephony hardware backends."""

from __future__ import annotations

import abc
from enum import IntEnum
from typing import Optional


class CallState(IntEnum):
    IDLE = 0
    RINGING = 1
    ACTIVE = 2
    DIALING = 3


class TelephonyBackend(abc.ABC):
    """All hardware backends must implement this interface."""

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Prepare the hardware (open ports, start processes, etc.)."""

    @abc.abstractmethod
    async def dial(self, number: str) -> bool:
        """Dial a phone number. Return True if the call is connected."""

    @abc.abstractmethod
    async def answer(self) -> bool:
        """Answer an incoming call."""

    @abc.abstractmethod
    async def hangup(self) -> bool:
        """Hang up the current call."""

    @abc.abstractmethod
    async def read_audio(self, num_samples: int) -> Optional[bytes]:
        """
        Read uplink audio (caller's voice) as raw PCM bytes.
        PCM format: 8kHz, 16-bit signed LE, mono.
        Returns None if no data available.
        """

    @abc.abstractmethod
    async def write_audio(self, data: bytes) -> None:
        """
        Write downlink audio (AI voice) as raw PCM bytes.
        PCM format: 8kHz, 16-bit signed LE, mono.
        """

    @abc.abstractmethod
    async def get_state(self) -> CallState:
        """Return the current call state."""

    @abc.abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the hardware is functional."""

    async def clear_playback(self) -> None:
        """Clear any queued playback audio (barge-in). Optional."""

    async def shutdown(self) -> None:
        """Release all hardware resources."""

    def device_info(self) -> dict:
        """Return a dict describing the device for the web dashboard."""
        return {
            "type": type(self).__name__,
            "healthy": self.is_healthy(),
        }
