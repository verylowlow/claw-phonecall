---
name: phone_call
description: "AI 电话 Agent — 基于真实安卓手机的智能外呼/接听，对齐 @openclaw/voice-call：句末 ASR → Agent 回复 → TTS 分帧下行，支持 barge-in 打断。"
version: "2.0.0"
author: "AI Phone Agent Team"
tags:
  - phone
  - call
  - ai
  - telephony
  - voice-call
  - barge-in
tools:
  - name: bash
    description: "执行系统命令，运行 Python Skill 脚本"
---

# AI 电话 Agent Skill

你是 AI 电话 Agent，通过真实安卓手机进行智能外呼与接听。核心对话循环对齐 **@openclaw/voice-call** 插件：

1. **句末检测**：`UtteranceSegmenter` 在用户停顿 ≥ 750ms 后产出整段 PCM
2. **ASR 转写**：整段 PCM 送 ASR（火山/Whisper）得到文本
3. **Agent 回复**：`openclaw_bridge` 调 Gateway `POST /v1/responses`（非流式），拉取完整回复
4. **TTS 下行**：合成语音按 20ms 分帧入队播放
5. **Barge-in**：用户开口即清空 TTS 队列，打断 Agent 播报

## 功能

| 功能 | 说明 |
|------|------|
| 外呼 | 主动拨打指定号码，自动播放欢迎语 |
| 接听 | 监听来电，自动接听并启动对话 |
| AI 对话 | 句末 ASR → Agent 回复 → TTS |
| 打断 | 用户开口即中断 TTS（barge-in） |
| 通话记录 | SQLite 存储，HTTP API 查询 |

## 使用方法

### 1. 发起外呼

当用户说「拨打 XXX」或「给 XXX 打电话」时：

```bash
python -m src.phone_skill call <电话号码>
```

示例：

```bash
python -m src.phone_skill call 13800138000
```

或通过 CLI：

```bash
python -m src outbound 13800138000
```

### 2. 监听来电

```bash
python -m src inbound
```

### 3. 挂断电话

```bash
python -m src.cli hangup
```

### 4. 查看通话状态

```bash
python -m src.cli status
```

### 5. 组件自检

```bash
python -m src.phone_skill test
```

## 事件流

PhoneSkill 以异步生成器方式持续 yield 事件，每条为 JSON：

```json
{"event": "status", "status": "dialing", "phone": "13800138000"}
{"event": "status", "status": "connecting"}
{"event": "status", "status": "call_started"}
{"event": "user_speaking", "text": "你好，我想咨询一下...", "final": true}
{"event": "agent_text", "text": "您好，请问有什么可以帮您？"}
{"event": "agent_responding", "text": "您好，请问有什么可以帮您？"}
{"event": "status", "status": "barge_in"}
{"event": "status", "status": "ended"}
```

### 事件类型

| 事件 | 说明 |
|------|------|
| `status:dialing` | 正在拨号 |
| `status:connecting` | 等待接通 |
| `status:call_started` | 通话建立，欢迎语已播放 |
| `status:barge_in` | 用户打断了 TTS 播放 |
| `status:ended` | 通话结束 |
| `status:failed` | 失败（附 `reason`） |
| `user_speaking` | ASR 转写结果（`final: true`） |
| `agent_text` | Agent 原始回复文本（TTS 播放前） |
| `agent_responding` | TTS 播放完成 |

## 代码调用

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
    finally:
        await skill.shutdown()

asyncio.run(main())
```

## 环境配置

复制 `.env.example` → `.env` 并填写：

| 变量 | 说明 |
|------|------|
| `VOLC_ASR_APP_KEY` | 火山引擎 ASR（三项必填） |
| `VOLC_ASR_ACCESS_TOKEN` | |
| `VOLC_ASR_SECRET_KEY` | |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw Gateway Token（可选，未填走 mock） |
| `OPENCLAW_GATEWAY_URL` | Gateway 地址，默认 `http://127.0.0.1:18789` |
| `OPENCLAW_AGENT_ID` | Agent ID，默认 `main` |
| `PHONE_SKILL_MOCK_REPLY` | 未连 Gateway 时的占位回复 |

## 关键配置（`src/config.py`）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `utterance_end_silence_ms` | 750 | 句末静音阈值（ms），越小响应越快但容易截断 |
| `utterance_min_speech_ms` | 250 | 最短有效语音，过滤噪声 |
| `tts_frame_ms` | 20 | TTS 分帧大小，越小打断延迟越低 |
| `max_audio_duration_ms` | 15000 | 单句最长录音 |
| `welcome_message` | 喂，您好，请问哪位？ | 接通后自动播放 |
| `filler_phrases` | ["嗯","好的","我在听"] | 填充词预缓存列表 |

## HTTP API

PhoneSkill 在 `0.0.0.0:8080` 提供通话记录 API：

```bash
# 查询所有通话记录
curl http://localhost:8080/api/calls

# 按手机号查询
curl "http://localhost:8080/api/calls?phone=13800138000"

# 健康检查
curl http://localhost:8080/health
```

## 架构图

```
 用户语音（手机上行 PCM）
       │
       ▼
 ┌──────────────────┐
 │  AudioCapture    │  scrcpy --record=- | ffmpeg → 16kHz s16le
 └────────┬─────────┘
          │ PCM chunk
          ▼
 ┌──────────────────┐
 │ VAD + Utterance   │  能量滞回 + Silero VAD
 │ Segmenter         │  句末静音 ≥ 750ms → finalize
 │                   │  speech_just_started → barge-in
 └────────┬─────────┘
          │ 整段 PCM                    │ barge-in
          ▼                             ▼
 ┌──────────────────┐          ┌──────────────────┐
 │  ASR (火山/Whisper)│          │  AudioPlayer     │
 │  → user_text     │          │  .barge_in()     │
 └────────┬─────────┘          │  清空 TTS 队列    │
          │                    └──────────────────┘
          ▼                             ▲
 ┌──────────────────┐                  │ TTS 分帧小块
 │  OpenClaw Gateway │                  │
 │  /v1/responses    │──── agent_text ──┤
 │  (非流式)         │                  │
 └──────────────────┘           ┌──────┴───────┐
                                │  TTS (edge)  │
                                └──────────────┘
```

## 前置条件

1. 手机已通过 USB 连接，`adb devices` 可见
2. 已安装 scrcpy、ffmpeg
3. 下行音频：外置声卡 → 对录线 → 手机麦/耳机口
4. 已安装依赖：`pip install -r requirements.txt`

## 常见问题

**Q: 没有声音？**
检查 scrcpy/ffmpeg 路径，`adb devices` 是否有设备。

**Q: 对方听不到声音？**
检查下行链路：PC 声卡 → 对录线 → 手机麦/耳机口。

**Q: 未配 Gateway 怎么办？**
PhoneSkill 自动使用 `mock_reply`（可通过 `PHONE_SKILL_MOCK_REPLY` 自定义），适合本地调试。

**Q: 打断不够灵敏？**
减小 `tts_frame_ms`（如 10），使下行更小块；或降低 `UtteranceSegmenterConfig.energy_speech`。

**Q: HTTP API 无法访问？**
检查 PhoneSkill 是否已启动，端口 8080 是否被占用。
