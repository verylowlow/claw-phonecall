"""
SIM800C backend — 2G GSM module.

Hardware: SIM800C USB-to-GSM module (quad-band 850/900/1800/1900MHz).
Connection: SIM card + USB cable -> PC.

NOTE: SIM800C only supports 2G networks. China's carriers are phasing out 2G
(expected full shutdown ~2026). Use SIM7600 (4G) for production deployments.
This backend is provided for testing and legacy network scenarios.

The SIM800C typically exposes a single serial port for both AT commands and
PCM audio (shared channel). Audio is enabled via AT+CPCMREG=1 after a call
connects, and PCM data is multiplexed on the same serial port.
"""

from __future__ import annotations

import logging

from .simcom_base import SIMComBackend

logger = logging.getLogger(__name__)


class SIM800CBackend(SIMComBackend):

    _module_name = "SIM800C"

    async def _init_module(self) -> None:
        resp = await self._at_cmd("AT+CGMM")
        logger.info("[SIM800C] Module model: %s", resp.strip())

        await self._at_cmd("AT+CLVL=5")
        await self._at_cmd("AT+CMIC=0,10")

        await self._at_cmd("AT+CLIP=1")

        resp = await self._at_cmd("AT+CREG?")
        if ",1" in resp or ",5" in resp:
            logger.info("[SIM800C] Registered on 2G network")
        else:
            logger.warning("[SIM800C] Not registered on network: %s", resp)
