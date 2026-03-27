"""
Filler Cache - 填充词缓存模块
启动时预合成填充词音频，运行时直接使用缓存
"""

import asyncio
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class FillerCache:
    """
    填充词缓存
    启动时预合成填充词音频，运行时直接使用缓存
    """

    def __init__(self, tts_manager):
        """
        初始化填充词缓存

        Args:
            tts_manager: TTS 管理器实例
        """
        self._tts = tts_manager
        self._cache: Dict[str, bytes] = {}

    async def preload(self, filler_phrases: List[str]) -> None:
        """
        预加载填充词音频

        Args:
            filler_phrases: 填充词列表
        """
        logger.info(f"Preloading {len(filler_phrases)} filler phrases...")

        tasks = []
        for phrase in filler_phrases:
            if phrase not in self._cache:
                tasks.append(self._preload_phrase(phrase))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Filler cache preloaded: {len(self._cache)} phrases")

    async def _preload_phrase(self, phrase: str) -> None:
        """
        预加载单个填充词

        Args:
            phrase: 填充词文本
        """
        try:
            audio_data = await self._synthesize_phrase(phrase)
            if audio_data:
                self._cache[phrase] = audio_data
                logger.debug(f"Preloaded filler: {phrase}")
        except Exception as e:
            logger.warning(f"Failed to preload filler '{phrase}': {e}")

    async def _synthesize_phrase(self, phrase: str) -> Optional[bytes]:
        """
        合成填充词音频

        Args:
            phrase: 填充词文本

        Returns:
            bytes: 音频数据
        """
        audio_chunks = []

        async for chunk in self._tts.synthesize(phrase):
            audio_chunks.append(chunk)

        if audio_chunks:
            return b"".join(audio_chunks)
        return None

    def get(self, text: str) -> Optional[bytes]:
        """
        获取填充词音频

        Args:
            text: 填充词文本

        Returns:
            bytes: 音频数据，不存在则返回 None
        """
        return self._cache.get(text)

    def preload_sync(self, filler_phrases: List[str]) -> None:
        """
        同步预加载（阻塞）

        Args:
            filler_phrases: 填充词列表
        """
        asyncio.run(self.preload(filler_phrases))

    def has(self, text: str) -> bool:
        """
        检查填充词是否已缓存

        Args:
            text: 填充词文本

        Returns:
            bool: 是否已缓存
        """
        return text in self._cache

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    @property
    def size(self) -> int:
        """
        缓存的填充词数量

        Returns:
            int: 数量
        """
        return len(self._cache)