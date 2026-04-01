"""
SIM7600 backend — 4G LTE module (recommended for production).

Hardware: SIM7600G-H / SIM7600CE-T USB Dongle or breakout board.
Connection: SIM card + USB cable -> PC.

The SIM7600 exposes multiple USB endpoints when connected:
  - /dev/ttyUSB0 (or COM3) — Diagnostic port
  - /dev/ttyUSB1 (or COM4) — NMEA GPS port
  - /dev/ttyUSB2 (or COM5) — AT command port
  - /dev/ttyUSB3 (or COM6) — PPP/Audio data port

On Windows these map to separate COM ports. The `at_port` should be the AT
command port and `audio_port` the data port for PCM audio.

Key AT commands specific to SIM7600 (beyond the shared SIMCom base):
  AT+CPCMBANDWIDTH=1,1  — set codec bandwidth (fixes audio issues)
  AT+CSDVC=1            — select earphone audio path
  AT+CNSMOD?            — query current network mode (LTE/3G/2G)
"""

from __future__ import annotations

import logging

from .simcom_base import SIMComBackend

logger = logging.getLogger(__name__)


class SIM7600Backend(SIMComBackend):

    _module_name = "SIM7600"

    async def _init_module(self) -> None:
        resp = await self._at_cmd("AT+CGMM")
        logger.info("[SIM7600] Module model: %s", resp.strip())

        await self._at_cmd("AT+CPCMBANDWIDTH=1,1")

        await self._at_cmd("AT+CLVL=5")
        await self._at_cmd("AT+CSDVC=3")

        await self._at_cmd("AT+CLIP=1")

        resp = await self._at_cmd("AT+CNSMOD?")
        logger.info("[SIM7600] Network mode: %s", resp.strip())

        resp = await self._at_cmd("AT+CREG?")
        if ",1" in resp or ",5" in resp:
            logger.info("[SIM7600] Registered on network")
        else:
            logger.warning("[SIM7600] Not registered: %s", resp)
