"""
AI Phone Agent - 音频捕获模块
AudioCapture: 通过 scrcpy 流式捕获安卓手机音频

使用方案：scrcpy --record=- | ffmpeg 实时转换后通过 stdout 输出
"""

import subprocess
import threading
import logging
import os
import time
from collections import deque
from typing import Optional, Generator, Deque

from . import config

logger = logging.getLogger(__name__)


class AudioCaptureError(Exception):
    """音频捕获异常"""
    pass


def _stderr_reader(proc: subprocess.Popen, label: str, sink: Deque[str]) -> None:
    """在后台读取子进程 stderr，避免 PIPE 塞满导致阻塞。"""
    if proc.stderr is None:
        return

    def run() -> None:
        try:
            for line in iter(proc.stderr.readline, b""):
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                sink.append(text)
                logger.debug("[%s] %s", label, text)
        except Exception as e:
            logger.debug("%s stderr reader ended: %s", label, e)

    threading.Thread(target=run, daemon=True).start()


class AudioCapture:
    """
    音频捕获器
    使用 scrcpy --record=- 输出到 stdout，通过 ffmpeg 实时转换
    """

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id
        self._scrcpy_process: Optional[subprocess.Popen] = None
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._running = threading.Event()
        self._scrcpy_stderr: Deque[str] = deque(maxlen=200)
        self._ffmpeg_stderr: Deque[str] = deque(maxlen=200)
        self.last_error: Optional[str] = None

        self.sample_rate = config.AUDIO_CONFIG["sample_rate"]
        self.channels = config.AUDIO_CONFIG["channels"]

        logger.info("AudioCapture initialized for device: %s", device_id or "default")

    def _build_scrcpy_command(self) -> list:
        scrcpy = config.get_tool_path("scrcpy")
        cmd = [scrcpy, "--no-video", "--no-control"]

        if self.device_id:
            cmd.extend(["-s", self.device_id])

        cmd.extend(
            [
                "--audio-source",
                config.SCRCPY_CONFIG.get("audio_source", "voice-performance"),
                "--audio-codec",
                config.SCRCPY_CONFIG.get("audio_codec", "opus"),
                "--audio-bit-rate",
                str(config.SCRCPY_CONFIG.get("audio_bit_rate", 128000)),
                "--record-format",
                config.SCRCPY_CONFIG.get("record_format", "mkv"),
                "--record",
                "-",
            ]
        )

        return cmd

    def _build_ffmpeg_command(self) -> list:
        ffmpeg = config.get_tool_path("ffmpeg")
        return [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "matroska",
            "-i",
            "pipe:0",
            "-ar",
            str(self.sample_rate),
            "-ac",
            str(self.channels),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ]

    @staticmethod
    def _popen_kw() -> dict:
        # Windows 下避免控制台窗口闪烁
        kw: dict = {}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return kw

    def start_capture(self) -> None:
        if self._running.is_set():
            logger.warning("Audio capture already running")
            return

        self.last_error = None
        self._scrcpy_stderr.clear()
        self._ffmpeg_stderr.clear()

        try:
            scrcpy_cmd = self._build_scrcpy_command()
            ffmpeg_cmd = self._build_ffmpeg_command()

            logger.info("Starting scrcpy: %s", " ".join(scrcpy_cmd))
            logger.info("Starting ffmpeg: %s", " ".join(ffmpeg_cmd))

            popen_kw = self._popen_kw()

            # stdout 必须为二进制：PCM/Matroska 流不能用 text 模式解码
            self._scrcpy_process = subprocess.Popen(
                scrcpy_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_kw,
            )
            _stderr_reader(self._scrcpy_process, "scrcpy", self._scrcpy_stderr)

            self._ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=self._scrcpy_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_kw,
            )
            _stderr_reader(self._ffmpeg_process, "ffmpeg", self._ffmpeg_stderr)

            if self._scrcpy_process.stdout:
                self._scrcpy_process.stdout.close()

            time.sleep(1)

            if self._scrcpy_process.poll() is not None:
                tail = "\n".join(self._scrcpy_stderr)
                self.last_error = tail or "scrcpy exited with no stderr"
                logger.error("scrcpy terminated immediately. stderr tail:\n%s", tail)
                self._cleanup_processes()
                raise AudioCaptureError("scrcpy process terminated immediately")

            if self._ffmpeg_process.poll() is not None:
                tail = "\n".join(self._ffmpeg_stderr)
                self.last_error = tail or "ffmpeg exited with no stderr"
                logger.error("ffmpeg terminated immediately. stderr tail:\n%s", tail)
                self._cleanup_processes()
                raise AudioCaptureError("ffmpeg process terminated immediately")

            self._running.set()
            logger.info("Audio capture started")

        except FileNotFoundError as e:
            self.last_error = str(e)
            raise AudioCaptureError(f"scrcpy or ffmpeg not found: {e}") from e
        except AudioCaptureError:
            raise
        except Exception as e:
            self.last_error = str(e)
            raise AudioCaptureError(f"Failed to start audio capture: {e}") from e

    def _cleanup_processes(self) -> None:
        self._running.clear()
        for proc in (self._ffmpeg_process, self._scrcpy_process):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._ffmpeg_process = None
        self._scrcpy_process = None

    def read(self, timeout: float = 0.1) -> Optional[bytes]:
        if not self._running.is_set():
            return None

        if not self._ffmpeg_process or not self._ffmpeg_process.stdout:
            return None

        try:
            chunk_size = config.AUDIO_CONFIG.get("chunk_size", 4096)
            data = self._ffmpeg_process.stdout.read(chunk_size)
            return data if data else None
        except Exception as e:
            logger.debug("Read audio error: %s", e)
            return None

    def get_audio_stream(self) -> Generator[bytes, None, None]:
        if not self._running.is_set():
            raise AudioCaptureError("Audio capture not started")

        logger.info("Starting audio stream generation")

        while self._running.is_set():
            if self._scrcpy_process and self._scrcpy_process.poll() is not None:
                tail = "\n".join(self._scrcpy_stderr)
                self.last_error = tail or "scrcpy process ended"
                logger.error("scrcpy process terminated. stderr tail:\n%s", tail)
                break

            if self._ffmpeg_process and self._ffmpeg_process.poll() is not None:
                tail = "\n".join(self._ffmpeg_stderr)
                self.last_error = tail or "ffmpeg process ended"
                logger.error("ffmpeg process terminated. stderr tail:\n%s", tail)
                break

            audio_data = self.read()
            if audio_data:
                yield audio_data
            else:
                time.sleep(0.05)

        logger.info("Audio stream generation ended")

    def stop_capture(self) -> None:
        if not self._running.is_set() and not self._scrcpy_process:
            return

        logger.info("Stopping audio capture...")
        self._running.clear()

        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._ffmpeg_process.kill()
            except Exception:
                pass
            self._ffmpeg_process = None

        if self._scrcpy_process:
            try:
                self._scrcpy_process.terminate()
                self._scrcpy_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._scrcpy_process.kill()
            except Exception:
                pass
            self._scrcpy_process = None

        logger.info("Audio capture stopped")

    def is_healthy(self) -> bool:
        """检查 scrcpy/ffmpeg 管道是否仍在运行（进程未退出）。"""
        if not self._running.is_set():
            return False
        if self._scrcpy_process and self._scrcpy_process.poll() is not None:
            return False
        if self._ffmpeg_process and self._ffmpeg_process.poll() is not None:
            return False
        return True

    def is_running(self) -> bool:
        return self._running.is_set()

    def __enter__(self):
        self.start_capture()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_capture()


def create_audio_capture(device_id: Optional[str] = None) -> AudioCapture:
    return AudioCapture(device_id=device_id)
