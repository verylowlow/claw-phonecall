"""
固定话术 PCM 磁盘缓存。

首次运行时通过 TTS 生成 16kHz s16le PCM 并写入 cache/audio/{key}.pcm，
后续运行直接读文件，实现零延迟播放。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from . import config

logger = logging.getLogger(__name__)

_CACHE_DIR = config.PROJECT_ROOT / "cache" / "audio"


class StaticAudioCache:
    """管理固定话术的 PCM 磁盘缓存。"""

    def __init__(self, tts_manager=None, cache_dir: Optional[Path] = None):
        self._tts = tts_manager
        self._dir = cache_dir or _CACHE_DIR
        self._mem: Dict[str, bytes] = {}

    def _pcm_path(self, key: str) -> Path:
        return self._dir / f"{key}.pcm"

    def get(self, key: str) -> Optional[bytes]:
        """从内存 → 磁盘获取 PCM，不存在返回 None。"""
        if key in self._mem:
            return self._mem[key]
        p = self._pcm_path(key)
        if p.is_file():
            data = p.read_bytes()
            if data:
                self._mem[key] = data
                return data
        return None

    async def ensure(self, key: str, text: str) -> bytes:
        """确保 key 对应的 PCM 存在（磁盘优先，否则 TTS 生成并保存）。"""
        cached = self.get(key)
        if cached:
            return cached

        if self._tts is None:
            raise RuntimeError("StaticAudioCache: TTS manager not set, cannot generate audio")

        logger.info("Generating static audio: key=%s text=%s", key, text[:40])
        chunks = []
        async for chunk in self._tts.synthesize(text):
            chunks.append(chunk)
        pcm = b"".join(chunks)

        if pcm:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._pcm_path(key).write_bytes(pcm)
            self._mem[key] = pcm
            logger.info("Saved static audio: %s (%d bytes)", key, len(pcm))
        else:
            logger.warning("TTS returned empty audio for key=%s", key)

        return pcm

    async def ensure_all(self, mapping: Dict[str, str]) -> None:
        """批量预生成。mapping = {key: text}。"""
        tasks = [self.ensure(k, v) for k, v in mapping.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (k, _), r in zip(mapping.items(), results):
            if isinstance(r, Exception):
                logger.warning("Failed to generate static audio key=%s: %s", k, r)

    def has(self, key: str) -> bool:
        if key in self._mem:
            return True
        return self._pcm_path(key).is_file()

    def keys_on_disk(self):
        """列出磁盘上已有的 key。"""
        if not self._dir.is_dir():
            return []
        return [p.stem for p in self._dir.glob("*.pcm")]
