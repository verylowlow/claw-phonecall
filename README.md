# AI Phone Agent

基于真实安卓机的智能外呼/接听 Agent。架构对齐 **@openclaw/voice-call** 插件：上行/下行双 task 并发；句末静音后一次性提交 ASR → OpenClaw Agent → TTS 分帧下行；支持 **barge-in**、**思考话术**、**道歉兜底**、**通话时长限制**、**固定话术零延迟预生成 PCM**。

## 方案概述

| 方向 | 实现 |
|------|------|
| 上行（手机 → PC） | scrcpy `voice-performance` + `--record=-` 管道，ffmpeg 转 16 kHz PCM |
| 下行（PC → 手机） | PyAudio 播放至外置声卡，对录线进手机麦/耳机口 |
| 控制 | `adb shell` 拨号、接听、挂断、`dumpsys` 读状态 |
| AI 对话 | 上行 task（读音频→VAD→segmenter）+ 下行 task（Gateway→TTS）并发；`asyncio.to_thread` 避免阻塞 |
| 打断 | `speech_just_started` 信号 → `AudioPlayer.barge_in()` 清队列 |
| 兜底 | Gateway 3s 未返回→思考话术；10s 无输出→循环道歉；通话超限→告别+挂断 |
| 固定话术 | `StaticAudioCache` 预生成 PCM 到 `cache/audio/`，运行时零延迟直播 |

> **注意**：scrcpy 建议在 **建立通话前** 启动；具体顺序见 `docs/test/` 下测试报告。

## 对话流程（Voice-call 风格）

```
 ┌──────────┐         ┌────────────────────┐         ┌──────────────┐
 │  手机上行  │  PCM   │   UtteranceSegmenter│ 整段PCM │   ASR        │
 │ scrcpy    │───────▶│  句末静音 ≥ 750ms   │────────▶│ (火山/Whisper)│
 │ + ffmpeg  │        │  speech_just_started│         └──────┬───────┘
 └──────────┘        └────────────────────┘                │ user_text
                           │ barge-in                       ▼
                           ▼                        ┌──────────────┐
                    ┌──────────────┐                │ OpenClaw     │
                    │ AudioPlayer  │   agent_text   │ Gateway      │
                    │ .barge_in()  │◀───────────────│ /v1/responses│
                    │ 清空 TTS 队列 │                └──────────────┘
                    └──────┬───────┘                        │
                           │ TTS 分帧小块                    │
                           ▼                                │
                    ┌──────────────┐                        │
                    │ 外置声卡 →   │                        │
                    │ 手机麦克风   │                        │
                    └──────────────┘
```

1. **VAD + 能量滞回** 检测是否有语音
2. `UtteranceSegmenter` 在用户停顿 ≥ `end_silence_ms`（默认 750ms）后 finalize 整段 PCM
3. ASR 转写 → 调用 `openclaw_bridge.request_agent_text`（非流式 `POST /v1/responses`）
4. TTS 合成 → 按 `tts_frame_ms`（默认 20ms）切小块入播放队列
5. 用户再次开口（`speech_just_started`）时，`AudioPlayer.barge_in()` 清空队列

## 项目结构

```
agentcalls/
├── src/
│   ├── __init__.py
│   ├── __main__.py            # python -m src
│   ├── config.py              # 配置、工具路径、.env、日志
│   ├── phone_controller.py    # ADB 通话控制
│   ├── audio_capture.py       # scrcpy + ffmpeg 捕获（二进制管道）
│   ├── audio_player.py        # PyAudio 播放 + barge_in()
│   ├── voice_utterance.py     # UtteranceSegmenter 句末分段
│   ├── openclaw_bridge.py     # OpenClaw Gateway HTTP 桥接（timeout 可配）
│   ├── static_audio_cache.py  # 固定话术 PCM 磁盘缓存
│   ├── ai_pipeline.py         # VAD / ASR / TTS 管理器
│   ├── volc_asr.py            # 火山引擎流式 ASR（可选）
│   ├── phone_skill.py         # PhoneSkill 主循环（Voice-call 风格）
│   ├── humanization.py        # 拟人化（填充词等）
│   ├── filler_cache.py        # TTS 填充词预缓存
│   ├── audio_buffer.py        # PCM 环形缓冲
│   ├── call_record.py         # SQLite 通话记录
│   ├── http_api.py            # REST API 服务
│   └── cli.py                 # 命令行入口
├── tests/
│   ├── conftest.py
│   ├── test_config_and_tools.py
│   ├── test_voice_utterance.py  # 句末分段单测
│   ├── test_edge_cases.py       # 边缘场景单测（缓存/问候/健康检测）
│   ├── test_integration.py      # 冒烟测试
│   └── test_phone_real.py       # 真机测试（需 ADB）
├── skills/
│   └── phone_call/SKILL.md
├── docs/
├── requirements.txt
├── .env.example
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac
```

编辑 `.env`，按需填写：

| 变量 | 必填 | 说明 |
|------|------|------|
| `VOLC_ASR_APP_KEY` | ASR 必填 | 火山引擎 ASR 凭证（三项） |
| `VOLC_ASR_ACCESS_TOKEN` | ASR 必填 | |
| `VOLC_ASR_SECRET_KEY` | ASR 必填 | |
| `OPENCLAW_GATEWAY_TOKEN` | 可选 | OpenClaw Gateway Bearer Token |
| `OPENCLAW_GATEWAY_URL` | 可选 | 默认 `http://127.0.0.1:18789` |
| `OPENCLAW_AGENT_ID` | 可选 | Gateway Agent ID，默认 `main` |
| `OPENCLAW_SESSION_USER` | 可选 | 会话路由标识（PhoneSkill 会自动用外呼号码） |
| `PHONE_SKILL_MOCK_REPLY` | 可选 | 未配置 Gateway 时的占位回复 |
| `AGENTCALLS_SCRCPY` | 可选 | scrcpy 路径（未设则用项目内或 PATH） |
| `AGENTCALLS_FFMPEG` | 可选 | ffmpeg 路径 |
| `AGENTCALLS_ADB` | 可选 | adb 路径 |

### 3. 外部工具

- [scrcpy](https://github.com/Genymobile/scrcpy)（可将 Windows 发行版放在项目 `scrcpy-win64-v3.3.3/` 下）
- [ffmpeg](https://ffmpeg.org/)
- Android [platform-tools](https://developer.android.com/studio/releases/platform-tools)（`adb`）

### 4. 运行测试

```bash
pytest                             # 单元 + 冒烟
python tests/test_integration.py   # 集成（不需要真机）
```

真机测试（需要 ADB 连接手机）：

```bash
set RUN_REAL_PHONE_TESTS=1
pytest tests/test_phone_real.py -v
```

### 5. CLI

```bash
python -m src outbound 13800138000   # 外呼
python -m src inbound                # 监听来电
python -m src test                   # 组件自检
```

### 6. 直接运行 PhoneSkill

```bash
python -m src.phone_skill call 13800138000
python -m src.phone_skill test
```

## 使用示例（代码）

```python
import asyncio
from src.phone_skill import PhoneSkill
from src.config import configure_logging

configure_logging()

async def main():
    skill = PhoneSkill()
    await skill.initialize()
    try:
        async for event in skill.phone_call("13800138000"):
            print(event)
            # {"event": "status", "status": "barge_in"}
            # {"event": "user_speaking", "text": "...", "final": true}
            # {"event": "agent_text", "text": "..."}
            # {"event": "agent_responding", "text": "..."}
    finally:
        await skill.shutdown()

asyncio.run(main())
```

## 事件流

| 事件 | 字段 | 说明 |
|------|------|------|
| `status:dialing` | phone | 正在拨号 |
| `status:connecting` | | 等待接通 |
| `status:call_started` | | 通话建立 |
| `status:barge_in` | | 用户打断了 TTS |
| `status:thinking_played` | | 播放了思考话术 |
| `status:apology_played` | | 播放了道歉话术 |
| `status:max_duration_reached` | | 通话时长超限 |
| `status:capture_lost` | | 音频管道断裂 |
| `status:ended` | | 通话结束 |
| `status:failed` | reason | 失败原因 |
| `user_speaking` | text, final | ASR 转写结果 |
| `agent_text` | text | Agent 原始回复文本 |
| `agent_responding` | text | TTS 播放完成 |
| `call_summary` | phone, duration, turns | 通话结束摘要 |

## 核心配置（`src/config.py`）

```python
CALL_CONFIG = {
    "agent_name": "小甜甜",
    "max_call_duration": 600,              # 通话时长上限（秒）
    "gateway_timeout_s": 10,               # Gateway 硬超时
    "thinking_delay_ms": 3000,             # N ms 后播思考话术
    "apology_interval_s": 10,              # 无输出 N s 后循环道歉
    "utterance_end_silence_ms": 750.0,     # 句末静音阈值
    "tts_frame_ms": 20,                    # TTS 分帧
    # welcome_templates / thinking_phrases / apology_message / farewell_message ...
}
```

## HTTP API

PhoneSkill 启动后在 `http_host:http_port`（默认 `0.0.0.0:8080`）提供 REST API：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/calls` | 通话记录列表（`?phone=xxx` 过滤） |
| GET | `/api/calls/{id}` | 单条记录 |
| GET | `/health` | 健康检查 |

## 音频与日志

- 上行管道全程 **二进制 stdout**（不用 `text=True`），stderr 后台 UTF-8 解码；失败时 `AudioCapture.last_error` 附 stderr 尾部。
- `configure_logging()` 控制台 + `logs/phone_agent.log` 均 UTF-8。

## 常见问题

**Q: 没有声音？**
检查 scrcpy/ffmpeg 是否安装，`adb devices` 是否有设备。

**Q: 对方听不到声音？**
检查下行链路：声卡 → 对录线 → 手机麦/耳机口。

**Q: 未配置 OpenClaw Gateway 会怎样？**
PhoneSkill 会用 `mock_reply()`（可通过 `PHONE_SKILL_MOCK_REPLY` 环境变量自定义），日志会提示。

**Q: 如何调整打断灵敏度？**
减小 `tts_frame_ms`（下行更小块，打断更快）和 `utterance_end_silence_ms`（更短静音即认为句末）。

**Q: 通话卡顿时用户听到什么？**
Gateway 3s 无响应 → 随机播放思考话术；10s 持续无输出 → 每 10s 循环播放道歉话术，直到恢复或用户挂断。

**Q: 固定话术首次启动慢？**
首次运行需 TTS 生成所有固定话术 PCM 并写入 `cache/audio/`，后续启动直接读文件（毫秒级）。

**Q: PyAudio 报 AttributeError？**
确认安装与 Python 版本匹配的 `pyaudio`，且项目中无同名 `pyaudio.py` 遮蔽。

## 许可证

MIT License
