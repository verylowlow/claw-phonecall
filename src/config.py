# AI Phone Agent - 配置模块
"""
项目配置管理。敏感信息仅从环境变量或 .env 读取，勿提交真实密钥。
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 可选：从 .env 加载（需安装 python-dotenv）
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ADB 配置
ADB_CONFIG = {
    "timeout": 30,
    "poll_interval": 0.5,
}

# 音频配置
AUDIO_CONFIG = {
    "sample_rate": 16000,
    "channels": 1,
    "format": "int16",
    "buffer_size": 1024,
    "chunk_size": 4096,
}

# scrcpy 配置
SCRCPY_CONFIG = {
    "audio_source": "voice-performance",
    "audio_codec": "opus",
    "audio_bit_rate": 128000,
    "max_fps": 30,
    "record_format": "mkv",
}

# VAD 配置
VAD_CONFIG = {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "min_silence_duration_ms": 300,
    "speech_pad_ms": 400,
}

# ASR 配置
ASR_CONFIG = {
    "model_size": "small",
    "device": "auto",
    "language": "zh",
    "provider": "volcengine",
}

# 火山引擎 ASR：仅使用环境变量（见 .env.example）
VOLC_ASR_CONFIG = {
    "app_key": os.environ.get("VOLC_ASR_APP_KEY", "").strip(),
    "access_token": os.environ.get("VOLC_ASR_ACCESS_TOKEN", "").strip(),
    "secret_key": os.environ.get("VOLC_ASR_SECRET_KEY", "").strip(),
}

# TTS 配置
TTS_CONFIG = {
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "pitch": "+0Hz",
    "volume": "+0%",
}

# 拟人化配置
HUMANIZATION_CONFIG = {
    "filler_threshold_ms": 1200,
    "filler_phrases": ["嗯", "好的", "我在听", "明白"],
    "barge_in_enabled": True,
}

# 通话控制配置
CALL_CONFIG = {
    "answer_delay": 2,
    "max_call_duration": 600,
    "max_audio_duration_ms": 15000,
    "http_host": "0.0.0.0",
    "http_port": 8080,

    # --- 问候语 ---
    "agent_name": "小甜甜",
    "welcome_templates": {
        "morning": "您好！上午好！我是AI客服{agent_name}。我来为您服务！通话中我会持续思考，如遇卡顿，请您见谅，多等我一会儿！",
        "afternoon": "您好！下午好！我是AI客服{agent_name}。我来为您服务！通话中我会持续思考，如遇卡顿，请您见谅，多等我一会儿！",
        "evening": "您好！晚上好！我是AI客服{agent_name}。我来为您服务！通话中我会持续思考，如遇卡顿，请您见谅，多等我一会儿！",
    },

    # --- 思考话术（Gateway 慢时插播） ---
    "thinking_delay_ms": 3000,
    "thinking_phrases": [
        "好的，我听到了，您稍等我想一下。",
        "嗯，我正在帮您查询，请稍候。",
        "收到，我思考一下马上回复您。",
    ],

    # --- 道歉话术（持续无输出兜底） ---
    "apology_interval_s": 10,
    "apology_message": "您好，非常抱歉，我的程序响应有些缓慢，麻烦您稍微等待或者直接挂机。",

    # --- 告别话术（通话时长超限） ---
    "farewell_message": "非常感谢您的来电，通话时间已到，再见！",

    # --- 填充词 ---
    "filler_phrases": ["嗯", "好的", "我在听"],

    # --- Gateway ---
    "gateway_timeout_s": 10,
    "gateway_fallback_reply": "抱歉，我这边信号不太好，您能再说一遍吗？",

    # --- 句末分句 ---
    "utterance_end_silence_ms": 750.0,
    "utterance_min_speech_ms": 250.0,

    # --- TTS 分帧 ---
    "tts_frame_ms": 20,
}

# 日志配置
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": PROJECT_ROOT / "logs" / "phone_agent.log",
}


def _default_scrcpy_path() -> str:
    """若项目内存在常见 scrcpy 目录则自动选用，否则依赖 PATH 中的 scrcpy。"""
    win_dir = PROJECT_ROOT / "scrcpy-win64-v3.3.3"
    for name in ("scrcpy.exe", "scrcpy"):
        p = win_dir / name
        if p.is_file():
            return str(p)
    return "scrcpy"


def get_tool_path(tool: str) -> str:
    """
    解析外部工具可执行文件路径。
    tool: scrcpy | ffmpeg | adb
    环境变量: AGENTCALLS_SCRCPY, AGENTCALLS_FFMPEG, AGENTCALLS_ADB
    """
    env_keys = {
        "scrcpy": "AGENTCALLS_SCRCPY",
        "ffmpeg": "AGENTCALLS_FFMPEG",
        "adb": "AGENTCALLS_ADB",
    }
    if tool not in env_keys:
        raise ValueError(f"Unknown tool: {tool}")
    override = os.environ.get(env_keys[tool], "").strip()
    if override:
        return override
    if tool == "scrcpy":
        return _default_scrcpy_path()
    if tool == "ffmpeg":
        return "ffmpeg"
    if tool == "adb":
        return "adb"
    return tool


def volc_asr_configured() -> bool:
    """火山 ASR 三项凭证是否均已配置。"""
    c = VOLC_ASR_CONFIG
    return bool(c.get("app_key") and c.get("access_token") and c.get("secret_key"))


def _parse_log_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)


def configure_logging(level: Optional[int] = None, force: bool = True) -> None:
    """
    配置根日志：控制台与文件均尽量使用 UTF-8，减少 Windows GBK 下 Unicode 崩溃。
    """
    import sys

    if level is None:
        level = _parse_log_level(str(LOG_CONFIG.get("level", "INFO")))

    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass

    fmt = logging.Formatter(LOG_CONFIG["format"])
    handlers: List[logging.Handler] = []

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    handlers.append(sh)

    log_file = LOG_CONFIG.get("file")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        handlers.append(fh)

    logging.basicConfig(level=level, handlers=handlers, force=force)


# 多手机配置
MULTI_PHONE_CONFIG = {
    "max_concurrent_calls": 3,
    "process_isolation": True,
}
