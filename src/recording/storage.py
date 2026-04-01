"""Recording storage management — cleanup old recordings."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from src.config import RECORDING_CONFIG

logger = logging.getLogger(__name__)


def get_recording_dir() -> Path:
    d = RECORDING_CONFIG["directory"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_recording_path(recording_path: str) -> Optional[Path]:
    """Resolve and validate a recording path."""
    p = Path(recording_path)
    if p.exists() and p.is_file():
        return p
    base = get_recording_dir()
    rel = base / recording_path
    if rel.exists() and rel.is_file():
        return rel
    return None


def cleanup_old_recordings(retain_days: Optional[int] = None) -> int:
    """Delete recordings older than retain_days. Returns count of deleted files."""
    days = retain_days or RECORDING_CONFIG["retain_days"]
    if days <= 0:
        return 0

    cutoff = time.time() - days * 86400
    rec_dir = get_recording_dir()
    deleted = 0

    for wav in rec_dir.rglob("*.wav"):
        if wav.stat().st_mtime < cutoff:
            try:
                wav.unlink()
                deleted += 1
            except Exception:
                logger.warning("Failed to delete old recording: %s", wav)

    for sub in rec_dir.iterdir():
        if sub.is_dir() and not any(sub.iterdir()):
            try:
                sub.rmdir()
            except Exception:
                pass

    if deleted:
        logger.info("Cleaned up %d old recordings (>%d days)", deleted, days)
    return deleted
