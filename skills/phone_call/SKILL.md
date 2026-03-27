---
name: phone_call
description: "AI 电话 Agent - 实现智能外呼、接听和对话功能。使用真实安卓手机进行通话，支持自动拨号、接听、语音识别、AI 对话和拟人化交互。"
version: "1.0.0"
author: "AI Phone Agent Team"
tags:
  - phone
  - call
  - ai
  - telephony
tools:
  - name: bash
    description: "执行系统命令，用于运行 Python 脚本"
---

# AI 电话 Agent Skill

你是 AI 电话 Agent，可以帮助用户通过真实的安卓手机进行智能外呼 和接听电话。

## 功能概述

1. **外呼 (Outbound)**: 主动拨打指定电话号码
2. **接听 (Inbound)**: 自动接听来电并启动 AI 对话
3. **语音对话**: 通过 ASR/TTS 实现实时语音交互
4. **通话控制**: 挂断、转接、保持等操作

## 使用方法

### 1. 发起外呼

当用户说「拨打 XXX」或「给 XXX 打电话」时：

```
请使用 bash 工具执行以下命令：
python D:\dev\agentcalls\src\phone_skill.py call <电话号码>

例如：python D:\dev\agentcalls\src\phone_skill.py call 13800138000
```

### 2. 处理来电

系统会自动监控来电，当有电话接入时自动接听并启动 AI 对话：

```
后台已启动电话监控，当有来电时会自动接听。
如需停止监控，请说「停止电话监控」。
```

### 3. 挂断电话

当用户说「挂断」或「结束通话」时：

```
请使用 bash 工具执行以下命令：
python D:\dev\agentcalls\src\cli.py hangup
```

### 4. 查看通话状态

当用户说「通话状态」或「当前通话」时：

```
请使用 bash 工具执行以下命令：
python D:\dev\agentcalls\src\cli.py status
```

### 5. 测试功能

当用户说「测试电话」或「检查配置」时：

```
请使用 bash 工具执行以下命令：
python D:\dev\agentcalls\src\phone_skill.py test
```

## 事件流架构

Python Skill 作为 OpenClaw Tool 长期运行，持续向 Agent 返回状态：

```python
# 事件流格式示例
{"event": "status", "status": "dialing", "phone": "13800138000"}
{"event": "status", "status": "connecting"}
{"event": "status", "status": "call_started"}
{"event": "user_speaking", "text": "你好，我想咨询一下..."}
{"event": "agent_responding", "text": "您好，请问有什么可以帮您？"}
{"event": "status", "status": "silence_detected"}
{"event": "status", "status": "ended"}
```

### 事件类型

| 事件 | 说明 |
|------|------|
| `status` | 通话状态变化 (dialing/connecting/call_started/ended/failed) |
| `user_speaking` | 用户说话结束，ASR 转写文本 |
| `agent_responding` | Agent 回复，TTS 播放完成 |

## HTTP API

启动 phone_skill 后，可通过 HTTP API 查询通话记录：

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/calls | 列出所有通话记录（分页） |
| GET | /api/calls?phone=xxx | 按手机号查询 |
| GET | /api/calls/{id} | 查看单条记录详情 |
| GET | /health | 健康检查 |

### 示例

```bash
# 查询所有通话记录
curl http://localhost:8080/api/calls

# 按手机号查询
curl "http://localhost:8080/api/calls?phone=13800138000"

# 查看单条记录
curl http://localhost:8080/api/calls/1
```

## 配置说明

如需修改配置，请编辑 `D:\dev\agentcalls\src\config.py`：

- `AUDIO_CONFIG`: 音频采样率、通道数
- `TTS_CONFIG`: TTS 音色、语速
- `CALL_CONFIG`: 欢迎语、接听延迟
- `VAD_CONFIG`: 语音活动检测参数
- `ASR_CONFIG`: 语音识别模型配置

### 填充词配置

在 `CALL_CONFIG` 中配置填充词：

```python
CALL_CONFIG = {
    "filler_phrases": ["嗯", "好的", "我在听", "明白"],
    # ...
}
```

## 技术架构

```
用户请求 → OpenClaw Agent
                    │
                    ▼ Tool: phone_call()
┌─────────────────────────────────────────────────────────────┐
│              Python Skill (硬件抽象层)                       │
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

## 注意事项

1. 确保手机已通过 USB 连接到电脑
2. 确保 ADB 已正确配置（运行 `adb devices` 验证）
3. 确保已安装必要依赖：`pip install -r requirements.txt`
4. 上行音频依赖 scrcpy，下行音频依赖物理声卡

## 常见问题

**Q: 没有声音怎么办？**
A: 检查 scrcpy 和 ffmpeg 是否已安装，检查物理音频链路是否正确连接。

**Q: 对方听不到声音怎么办？**
A: 检查下行音频链路（声卡 → 对录线 → 手机麦克风）。

**Q: 无法拨打电话怎么办？**
A: 运行 `adb devices` 确认手机已连接，检查手机设置中允许 ADB 调试。

**Q: HTTP API 无法访问怎么办？**
A: 检查 phone_skill 是否已启动，端口是否被占用（默认 8080）。