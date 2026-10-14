# AgentCallCenter

**Twilio 兼容的本地电话网关** — 让 OpenClaw 的 voice-call 插件复用全部 AI 能力（VAD、ASR、Agent、TTS、barge-in），音频走本地硬件，不依赖任何云 telephony 账号。

> A Twilio-compatible local telephony bridge. Point your OpenClaw `voice-call` plugin at
> this bridge instead of Twilio, and the AI voice stack keeps working — over your own
> hardware, on your own network.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 为什么需要它

Twilio 的 Media Streams 是目前最省事的实时语音接入方式，但它是**按分钟计费的云服务**——
把 AI 语音能力接到 PSTN 上，意味着每一通对话都要向境外服务商报数、报文字、报音频。

AgentCallCenter 把这一层搬回本地：对外暴露 Twilio 的 REST 契约，内部把音频接到
你手边的硬件（4G 模块、USB 语音调制解调器、安卓手机）。**上层的 OpenClaw 插件几乎不用改。**

```
OpenClaw voice-call <--REST/WebSocket--> AgentCallCenter Bridge <--硬件--> 电话线路
   (VAD/ASR/LLM/TTS)                (Twilio 兼容层)      (SIM7600/USB Modem/Android)
```

---

## 特性

| | |
|---|---|
| **Twilio REST 兼容** | 实现 `POST /2010-04-01/Accounts/{sid}/Calls.json`，解析 TwiML `<Stream>` |
| **多硬件后端** | SIM7600 4G LTE（推荐）/ SIM800C 2G / USB Voice Modem / Android / Mock |
| **双向音频** | 8 kHz μ-law ↔ 16-bit PCM，WebSocket 承载，自动重采样 |
| **barge-in** | 下行 `<clear>` 事件清空播放队列，对话打断不排队 |
| **双向录音** | 上行 + 下行分别录制，按号码归档为 WAV |
| **Web 管理后台** | 控制台面板 + 通话记录（搜索 / 播放 / 下载） |
| **零外部依赖** | μ-law 编解码自带纯 Python 兜底，`audioop` 不可用也能跑 |

---

## ⭐ Star 支持

如果这个项目帮你省掉了云 telephony 的账单，或者你正在做本地部署的 AI 语音，
**点一下 Star** —— 这是对本项目最实在的支持，也会让更多做同样事情的人找到它。

你的 Star 也帮我在真实场景里验证维护的价值。如果你愿意更进一步：

- **提 Issue**：报 bug 请附上模块型号（SIM7600 / SIM800C / USB Modem / Android）
  和 AT 口、音频口编号，这两项能省掉一整轮来回
- **带硬件的 PR 尤其欢迎**：`backends/` 是可插拔的，新增一个后端不需要动主流程
- **把你的话术/场景写进 Discussions**：AI 客服、催收、回访、预约，各行的差异很大

## 💬 Discussions

已经开启，几个常聊的话题方向：

|分类 | 适合聊什么 |
|---|---|
| Q&A | 接线、串口、拨号问题的排查 |
| Hardware | 各型号模块的实测表现 |
| Show and tell | 你搭的 Bridge 长什么样 |
| Ideas | 想接但还没支持的硬件 |

## 🤝 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。简单说：改代码请先开 Issue 讨论，
提交前跑 `python -m pytest tests/ -v`。

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/verylowlow/claw-phonecall.git
cd claw-phonecall
pip install -r requirements.txt
```

> Python 3.13 上 `audioop` 已被标准库移除。本项目内置纯 Python 的 G.711 μ-law
> 实现作为兜底，所以**即使 `audioop-lts` 装不上也不影响运行**。

### 2. 配置

```bash
cp .env.example .env
```

最少改一行：

```env
BRIDGE_BACKEND=mock      # 先用 mock 跑通链路，再换真实硬件
```

### 3. 启动

```bash
python -m src.server
```

- Twilio REST API：`http://127.0.0.1:8080`
- Web 管理后台：`http://127.0.0.1:8080`（`/` 控制台，`/records` 通话记录）

### 4. 让 voice-call 指向本 Bridge

```json5
{
  plugins: {
    entries: {
      "voice-call": {
        enabled: true,
        config: {
          provider: "twilio",
          fromNumber: "+8610000000",
          twilio: {
            accountSid: "LOCAL_BRIDGE",
            authToken: "local_token",
            apiBaseUrl: "http://127.0.0.1:8080"   // ← 指到本 Bridge
          },
          publicUrl: "http://127.0.0.1:8080/voice/webhook",
          streaming: { enabled: true, streamPath: "/voice/stream" }
        }
      }
    }
  }
}
```

上层插件不需要任何改动。

---

## 硬件后端

### SIM7600 4G LTE（推荐）

```env
BRIDGE_BACKEND=sim7600
SIMCOM_AT_PORT=COM5       # AT 命令口
SIMCOM_AUDIO_PORT=COM6    # PCM 音频口
SIMCOM_BAUD_RATE=115200
```

SIM7600G-H USB Dongle + 4G SIM 卡，插入 PC 的 USB 口即可。
它会枚举出多个 COM 口，在设备管理器里找 AT 口和 Audio 口。

### SIM800C 2G GSM（仅开发测试）

```env
BRIDGE_BACKEND=sim800c
SIMCOM_AT_PORT=COM3
# SIMCOM_AUDIO_PORT=      # SIM800C 单口复用，留空
```

⚠️ 2G 网络正在退网，只用于开发验证。

### USB Voice Modem（固网线路）

```env
BRIDGE_BACKEND=usb_modem
MODEM_PORT=COM3
```

接线：电话线 (RJ11) → USB Voice Modem → PC USB

### Android 手机

```env
BRIDGE_BACKEND=android
ANDROID_DEVICE_ID=       # 留空自动检测
```

接线：Android (USB + ADB) + 外接声卡 + 3.5mm 音频线

---

## 项目结构

```
src/
├── server.py                # 主入口（FastAPI + lifespan）
├── config.py                # 环境变量配置
├── bridge_manager.py        # 通话流程调度 + 媒体桥接循环
├── twilio_compat/           # Twilio 兼容层
│   ├── rest_api.py          # POST /Calls.json
│   ├── twiml_parser.py      # 解析 TwiML <Stream>
│   └── webhook.py           # 状态回调
├── media_stream/
│   ├── ws_client.py         # WebSocket 客户端（含重连）
│   ├── codec.py             # PCM ↔ μ-law ↔ base64
│   └── protocol.py          # Media Streams 消息
├── backends/                # 硬件后端（可插拔）
│   ├── base.py              # TelephonyBackend 抽象
│   ├── simcom_base.py       # SIMCom AT 命令 + URC + PCM 线程
│   ├── sim7600.py / sim800c.py
│   ├── usb_modem.py / android.py / mock.py
├── recording/               # 双向录音
├── db/models.py             # SQLite 持久化
└── web/                     # Web 管理后台
```

---

## 踩过的坑（都已在代码里修好）

这个仓库不是一次写完的 demo。下面几条是实际调试中确认并修复的问题，
如果你也要写自己的 telephony 后端，建议先读一遍：

**1. `ATD` 是异步的，收到 `OK` 不代表接通**
`ATD<number>;` 立刻回 `OK` 只表示"命令已接受"，真正的接通结果几百毫秒后才以
URC `VOICE CALL: BEGIN` 上报。如果 AT 命令循环在 `OK` 上break，接通事件永远读不到
→ **表现为拨不通，且没有任何报错**。代码里为此留了 `_URC_DRAIN_S` 收报窗口。

**2. URC 和命令回显混在同一个流里**
`BUSY` / `NO CARRIER` 既是结果码、又可能是 URC。混为一谈会让"呼叫失败"
被当成"收到一条无关通知"吞掉，桥接层继续往下走。
`_looks_like_urc()` 把两类行分开，结果码必须回给调用方。

**3. pyserial 不是线程安全的**
双口模块会起一个 URC 线程读 AT 口，和 `_at_cmd` 的读操作争抢同一个对象。
表现为偶发的"ATD 无响应"—— 极难复现。所有串口读写走 `_serial_lock`。

**4. 单口模块（SIM800C）不要起 URC 线程**
AT 口和音频口是同一个，起线程只会三方争抢。单口时接通事件改由 `_at_cmd`
内联摘取，写进 `_pending_urc` 供 `_wait_for_connect` 复查。

**5. `hangup()` 不能无条件返回成功**
`ATH` 回`ERROR` 时若仍上报成功，桥接层会以为已挂断，实际线路还占着 ——
表现是"下一通拨不通"。现在按响应区分： `OK` / `NO CARRIER` 算成功，其它算失败。

**6. μ-law 编码的位宽**
自写实现最容易错的是段边界表：输入先算术右移 2 位压到 14 bit，
段边界就是 0x3F…0x1FFF 而不是 0xFF…0x7FFF。
实测往返 SNR 37.1 dB、解码满量程 32124 才算对齐标准。

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## License

MIT — 见 [LICENSE](LICENSE)。

音频通路、Twilio 兼容层与硬件抽象均可独立复用。
商业 AI 能力（ASR / LLM / TTS）不在本仓库内，本项目只做**传输层**。