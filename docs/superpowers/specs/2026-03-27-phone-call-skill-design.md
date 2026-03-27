# AI 电话 Agent Skill 设计方案

**日期**: 2026-03-27
**状态**: 已评审
**基于**: projectmanager20260327.txt 问题清单

---

## 1. 背景与目标

### 1.1 项目背景

项目旨在实现一个 AI 电话 Agent，通过真实安卓手机进行智能外呼/接听电话。核心思路：

- **OpenClaw** 负责业务逻辑和决策（大脑）
- **Python Skill** 负责硬件抽象（躯干）：音频捕获、ASR、TTS、电话控制

### 1.2 问题清单

| 优先级 | 问题/需求 | 解决方案 |
|--------|-----------|----------|
| P0 | `LLMClient` 是纯占位代码 | 移除，LLM 逻辑移至 OpenClaw 端 |
| P0 | ASR→LLM→TTS 闭环断裂 | 改造为事件流架构 |
| P1 | 没有语音段累积 | VAD 检测到静音段后送 ASR |
| P1 | 填充词没有预缓存 | 启动时 TTS 预合成 |
| P2 | scrcpy/ADB 断线重连 | 预留机制 |
| P2 | 对话上下文管理 | OpenClaw Session 管理 |
| P2 | 用户管理/通话记录 | SQLite + HTTP API |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ • 理解用户意图                                           ││
│  │ • 业务决策                                               ││
│  │ • Tool: phone_call (长期运行)                            ││
│  │ • Session 管理上下文                                     ││
│  └─────────────────────────────────────────────────────────┘│
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ Tool: phone_call(phone_number, purpose)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Python Skill (硬件抽象层)                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │AudioCapture  │───▶│    VAD       │───▶│     ASR      │  │
│  │  (scrcpy)    │    │ (语音活动检测)│    │  (转写文字)  │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                  │           │
│                    ┌──────────────┐              │           │
│                    │     TTS      │◀─────────────┘           │
│                    │  (语音合成)  │                         │
│                    └──────┬───────┘                         │
│                           │                                  │
│                    ┌──────▼───────┐                         │
│                    │PhoneController│◀── ADB                 │
│                    │ (电话控制)    │    (安卓手机)           │
│                    └──────────────┘                         │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐                      │
│  │  CallRecord  │    │ FillerCache  │                      │
│  │   (SQLite)   │    │ (填充词缓存)  │                      │
│  └──────────────┘    └──────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 事件流设计

Python Skill 作为长期运行的 Tool，持续向 OpenClaw Agent 返回状态：

```python
# 事件流格式
yield {"event": "status", "status": "dialing", "phone": "13800138000"}
yield {"event": "status", "status": "connecting"}
yield {"event": "status", "status": "call_started"}
yield {"event": "user_speaking", "text": "你好，我想咨询一下..."}
yield {"event": "agent_responding", "text": "您好，请问有什么可以帮您？"}
yield {"event": "status", "status": "silence_detected"}
yield {"event": "status", "status": "ended"}
```

---

## 3. 模块设计

### 3.1 PhoneController (电话控制)

**职责**: 通过 ADB 控制安卓手机进行拨号、接听、挂断

**接口**:
```python
from enum import Enum
from dataclasses import dataclass

class CallState(Enum):
    IDLE = "idle"
    DIALING = "dialing"
    RINGING = "ringing"
    OFFHOOK = "offhook"  # 通话中
    DISCONNECTED = "disconnected"

class PhoneController:
    def dial(self, phone_number: str) -> bool:
        """发起拨号"""

    def answer(self) -> bool:
        """接听来电"""

    def hangup(self) -> bool:
        """挂断电话"""

    def get_call_state(self) -> CallState:
        """获取通话状态"""

    def wait_for_state(self, target_state: CallState, timeout: float = 30) -> bool:
        """等待通话状态变化"""
```

### 3.2 AudioCapture (音频捕获)

**职责**: 通过 scrcpy 捕获手机通话音频

**接口**:
```python
from typing import Generator, Optional

class AudioCapture:
    def __init__(self, device_id: Optional[str] = None):
        """初始化音频捕获器"""

    def start(self) -> None:
        """启动音频捕获"""

    def stop(self) -> None:
        """停止音频捕获"""

    def read(self, chunk_size: int = 4096) -> Optional[bytes]:
        """读取一块音频数据"""

    def is_running(self) -> bool:
        """检查是否正在捕获"""
```

### 3.3 VADManager (语音活动检测)

**职责**: 使用 Silero VAD 检测语音开始和结束

**接口**:
```python
from dataclasses import dataclass
from typing import List

@dataclass
class VADResult:
    """VAD 检测结果"""
    is_speech: bool                          # 是否检测到语音
    speech_timestamps: List[dict]            # 语音时间段列表
    has_silence_after_speech: bool           # 是否有静音段（用于判断一句话结束）

class VADManager:
    def __init__(self):
        """初始化 VAD 管理器"""

    def load_model(self) -> None:
        """加载 VAD 模型"""

    def detect(self, audio_chunk: bytes) -> VADResult:
        """
        检测语音

        Args:
            audio_chunk: PCM 音频数据 (16kHz, 16bit, 单声道)

        Returns:
            VADResult: 检测结果
        """
```

### 3.4 ASRManager (语音识别)

**职责**: 使用 Faster-Whisper 将语音转写为文字

**接口**:
```python
class ASRManager:
    def __init__(self):
        """初始化 ASR 管理器"""

    def load_model(self) -> None:
        """加载 ASR 模型"""

    def transcribe(self, audio: bytes, language: str = "zh") -> str:
        """
        转写音频为文字

        Args:
            audio: PCM 音频数据
            language: 语言代码

        Returns:
            str: 转写文本
        """
```

### 3.5 TTSManager (语音合成)

**职责**: 使用 Edge-TTS 将文字转为语音

**接口**:
```python
from typing import AsyncGenerator

class TTSManager:
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        """初始化 TTS 管理器"""

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        异步合成语音

        Args:
            text: 要合成的文本

        Yields:
            bytes: 音频数据块
        """

    def synthesize_sync(self, text: str) -> bytes:
        """
        同步合成语音

        Args:
            text: 要合成的文本

        Returns:
            bytes: 完整音频数据
        """
```

### 3.6 AudioBuffer (语音段累积)

**职责**: 累积完整语音段，等待 VAD 检测到静音段后送 ASR

**接口**:
```python
class AudioBuffer:
    def __init__(self, max_duration_ms: int = 10000):
        """
        初始化音频缓冲区

        Args:
            max_duration_ms: 最大累积时长（毫秒）
        """

    def add(self, audio_chunk: bytes) -> None:
        """添加音频数据"""

    def is_complete(self, vad_result: VADResult) -> bool:
        """判断是否累积完成（一句话结束）"""

    def get_audio(self) -> bytes:
        """获取累积的音频数据"""

    def clear(self) -> None:
        """清空缓冲区"""

    def has_content(self) -> bool:
        """检查缓冲区是否有内容"""
```

### 3.7 FillerCache (填充词缓存)

**职责**: 启动时预合成填充词音频，运行时直接使用缓存

**接口**:
```python
from typing import List, Optional

class FillerCache:
    def __init__(self, tts_manager: TTSManager):
        """
        初始化填充词缓存

        Args:
            tts_manager: TTS 管理器实例
        """

    async def preload(self, filler_phrases: List[str]) -> None:
        """
        预加载填充词音频

        Args:
            filler_phrases: 填充词列表
        """

    def get(self, text: str) -> Optional[bytes]:
        """
        获取填充词音频

        Args:
            text: 填充词文本

        Returns:
            bytes: 音频数据，不存在则返回 None
        """
```

### 3.8 CallRecord (通话记录)

**职责**: 存储通话记录到 SQLite

**数据库表**:
```sql
CREATE TABLE call_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number VARCHAR(20) NOT NULL,
    call_time DATETIME NOT NULL,
    duration INTEGER DEFAULT 0,
    call_type VARCHAR(10),  -- 'inbound' / 'outbound'
    user_text TEXT,         -- 用户说的话 (ASR)
    agent_response TEXT,    -- Agent 回复
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_phone ON call_records(phone_number);
CREATE INDEX idx_call_time ON call_records(call_time);
```

**接口**:
```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class CallRecordData:
    """通话记录数据"""
    id: Optional[int]
    phone_number: str
    call_time: datetime
    duration: int
    call_type: str
    user_text: str
    agent_response: str

class CallRecord:
    def __init__(self, db_path: str = "call_records.db"):
        """初始化通话记录管理器"""

    def save(self, record: CallRecordData) -> int:
        """
        保存通话记录

        Returns:
            int: 记录 ID
        """

    def get_by_phone(self, phone_number: str) -> List[CallRecordData]:
        """按手机号查询通话记录"""

    def get_by_id(self, record_id: int) -> Optional[CallRecordData]:
        """按 ID 查询单条记录"""

    def get_all(self, limit: int = 100, offset: int = 0) -> List[CallRecordData]:
        """获取所有通话记录（分页）"""
```

### 3.9 HTTPServer (HTTP API 服务器)

**职责**: 提供通话记录的 HTTP 查询接口

**接口**:
```python
class HTTPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        """初始化 HTTP 服务器"""

    def register_call_record(self, call_record: CallRecord):
        """注册通话记录管理器"""

    def start(self):
        """启动服务器"""

    def stop(self):
        """停止服务器"""
```

**HTTP API 端点**:
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/calls | 列出所有通话记录（分页） |
| GET | /api/calls?phone=xxx | 按手机号查询 |
| GET | /api/calls/{id} | 查看单条记录详情 |
| GET | /health | 健康检查 |

---

## 4. 事件流流程

### 4.1 外呼流程

```
1. OpenClaw Agent 调用 Tool: phone_call(phone_number="138xxx")
2. Python Skill:
   a. yield {"event": "status", "status": "dialing"}
   b. phone_controller.dial(phone_number)
   c. yield {"event": "status", "status": "connecting"}
   d. 等待对方接听 (wait_for_state(OFFHOOK))
   e. yield {"event": "status", "status": "call_started"}
3. 进入通话循环 (见 4.2)
```

### 4.2 通话循环

```
while True:
    # 1. 捕获音频
    audio_chunk = audio_capture.read()

    # 2. VAD 检测
    vad_result = vad.detect(audio_chunk)
    audio_buffer.add(audio_chunk)

    # 3. 检测到一句话结束 (静音段)
    if vad_result.has_silence_after_speech and audio_buffer.has_content:
        # 4. ASR 转写
        user_text = asr.transcribe(audio_buffer.get_audio())
        audio_buffer.clear()

        # 5. 返回给 OpenClaw Agent
        yield {"event": "user_speaking", "text": user_text}

        # 6. 等待 Agent 回复 (通过某种方式接收)
        #    这里需要确定 Agent 如何返回回复
        #    可能方案:
        #    a. 通过 stdin/stdout 管道
        #    b. 通过文件/队列
        #    c. OpenClaw Tool 机制支持返回值

        agent_response = wait_for_agent_response()

        # 7. TTS 播放
        async for chunk in tts.synthesize(agent_response):
            audio_player.play(chunk)

        yield {"event": "agent_responding", "text": agent_response}

    # 8. 检查通话是否结束
    if phone_controller.get_call_state() == IDLE:
        yield {"event": "status", "status": "ended"}
        break
```

**待确定问题**: Agent 回复如何传递给 Python Skill？

可能的方案：
1. **文件/队列**: Python 写文件/队列，Agent 读取
2. **stdin/stdout**: 通过子进程管道
3. **HTTP API**: Python 启动简易 HTTP 服务

建议先采用 **方案 1 (文件/队列)** 实现，简化架构。

---

## 5. 数据流图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OpenClaw Agent                               │
│                                                                     │
│   Tool: phone_call(phone_number)                                    │
│                         │                                            │
│                         ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────┐│
│   │  Python Skill Process                                          ││
│   │                                                                 ││
│   │  ┌────────────┐    ┌───────────┐    ┌────────────┐            ││
│   │  │AudioCapture│───▶│    VAD    │───▶│AudioBuffer │            ││
│   │  └────────────┘    └───────────┘    └─────┬──────┘            ││
│   │                                             │                   ││
│   │                                             ▼                   ││
│   │                                    ┌────────────┐              ││
│   │                                    │    ASR     │              ││
│   │                                    └─────┬──────┘              ││
│   │                                          │                     ││
│   │                                          ▼                     ││
│   │   ┌────────────────────────────────────────────────────────┐  ││
│   │   │  yield {"event": "user_speaking", "text": "..."}       │──┼──┼──▶ OpenClaw
│   │   └────────────────────────────────────────────────────────┘  │  ││
│   │                                          │                     │  ││
│   │                                          │ Agent 回复          │  ││
│   │                                          │ (文件/队列)         │  ││
│   │                                          ▼                     │  ││
│   │                                    ┌────────────┐              │  ││
│   │                                    │    TTS     │              │  ││
│   │                                    └─────┬──────┘              │  ││
│   │                                          │                     │  ││
│   │                                          ▼                     │  ││
│   │                                    ┌────────────┐              │  ││
│   │                                    │AudioPlayer │              │  ││
│   │                                    └────────────┘              │  ││
│   │                                                                 ││
│   │   ┌────────────────────────────────────────────────────────┐  ││
│   │   │  yield {"event": "agent_responding", "text": "..."}    │──┼──────▶ OpenClaw
│   │   └────────────────────────────────────────────────────────┘  │  ││
│   │                                                                 │  ││
│   │   ┌────────────────────────────────────────────────────────┐  ││
│   │   │  CallRecord.save(...)  # 存储通话记录                  │  ││
│   │   └────────────────────────────────────────────────────────┘  │  ││
│   │                                                                 │  ││
│   └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. 文件结构

```
D:\dev\agentcalls\
├── src/
│   ├── __init__.py
│   ├── config.py           # 配置
│   ├── phone_controller.py # 电话控制 (已有，保留)
│   ├── audio_capture.py    # 音频捕获 (已有，保留)
│   ├── audio_player.py     # 音频播放 (已有，保留)
│   ├── vad.py              # 新增: VAD 管理
│   ├── asr.py              # 新增: ASR 管理
│   ├── tts.py              # 新增: TTS 管理
│   ├── audio_buffer.py     # 新增: 语音段累积
│   ├── filler_cache.py     # 新增: 填充词缓存
│   ├── call_record.py      # 新增: 通话记录存储
│   ├── http_api.py         # 新增: HTTP API 服务器
│   ├── cli.py              # CLI 入口 (已有)
│   └── phone_skill.py      # 新增: Skill 主程序 (事件流)
├── tests/
│   └── test_integration.py
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-03-27-phone-call-skill-design.md
├── skills/
│   └── phone_call/
│       └── SKILL.md        # Skill 定义
└── requirements.txt
```

---

## 7. 实现顺序

| 阶段 | 任务 | 说明 |
|------|------|------|
| 1 | 改造现有模块 | 保留 phone_controller, audio_capture, audio_player |
| 2 | 新增 VAD/ASR/TTS | 整合到 ai_pipeline.py 或拆分为独立模块 |
| 3 | 实现语音段累积 | AudioBuffer 类 |
| 4 | 改造为事件流 | phone_skill.py 长期运行 Tool |
| 5 | 实现填充词缓存 | FillerCache 类 |
| 6 | 实现通话记录 | CallRecord + SQLite |
| 7 | HTTP API | http_api.py |
| 8 | 改造 SKILL.md | 更新 Skill 定义 |

---

## 8. 待确定问题

~~1. **Agent 回复传递方式**: OpenClaw Agent 的回复如何传递给 Python Skill？~~
   - ~~建议: 文件/队列方式~~

   **更新**: 经过分析，OpenClaw Tool 支持直接返回值。当 Python Skill 执行 `yield` 时，OpenClaw Agent 会等待 Tool 返回结果。我们可以利用这个机制：
   - Python Skill yield `user_speaking` 事件后等待
   - OpenClaw Agent 处理完后，Tool 调用返回 Agent 的回复
   - Python Skill 收到回复后继续执行 TTS

2. **Skill 部署方式**: Python Skill 如何被 OpenClaw 加载？
   - 方案 A: 通过 bash 工具调用 Python 脚本（当前 SKILL.md 的方式）
   - 方案 B: 放置到 `~/.openclaw/workspace/skills/phone_call/` 作为原生 Skill
   - **建议**: 初期使用方案 A（bash 调用），简化实现

3. **填充词触发**: 填充词由谁决定播放时机？
   - **建议**: Python Skill 根据 VAD 结果决定，OpenClaw Agent 不需要知道

4. **实时性问题**: OpenClaw Tool 调用的等待机制可能影响实时性
   - 需要在实践中验证响应延迟是否满足通话需求
   - 如有延迟，可考虑异步通知机制

---

## 9. 验收标准

- [ ] 成功调用 `phone_call` Tool 发起外呼
- [ ] 用户说话后 ASR 转写文本返回给 Agent
- [ ] Agent 回复通过 TTS 播放
- [ ] 通话结束后通话记录保存到 SQLite
- [ ] HTTP API 可以查询通话记录

---

## 10. 参考资料

- OpenClaw 文档: https://docs.openclaw.ai
- OpenClaw GitHub: https://github.com/openclaw/openclaw
- Silero VAD: https://github.com/snakers4/silero-vad
- Faster-Whisper: https://github.com/SYSTRAN/faster-whisper