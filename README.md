# AgentCallCenter

**Twilio 兼容的本地电话网关** — 让 OpenClaw 的 voice-call 插件复用全部 AI 能力（VAD、ASR、Agent、TTS、barge-in），音频走本地硬件。

## 架构

```
OpenClaw voice-call <--REST/WebSocket--> AgentCallCenter Bridge <--硬件--> 电话线路
```

Bridge 对 voice-call 伪装成 Twilio：
- 实现 `POST /2010-04-01/Accounts/{sid}/Calls.json`（创建通话）
- 接收 TwiML 响应并解析 `<Stream>` WebSocket 地址
- 通过 WebSocket 与 voice-call 双向传输 mulaw 8kHz 音频
- 同时对接本地硬件（USB 语音调制解调器 / Android 手机 / SIP）

## 功能

- **多硬件后端**：USB Voice Modem (AT 指令)、Android (ADB + scrcpy)、Mock (测试)
- **双向录音**：自动录制上行+下行音频，按号码归档为 WAV
- **Web 管理后台**：控制台面板 + 通话记录列表（搜索、播放、下载）
- **SQLite 数据库**：通话记录、设备状态持久化

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 设置后端类型和 voice-call 地址
```

### 3. 启动服务

```bash
python -m src.server
```

- **Twilio REST API**：`http://127.0.0.1:8080`
- **Web 管理后台**：`http://127.0.0.1:8080`（控制台面板 `/`，通话记录 `/records`）

## voice-call 配置

在 OpenClaw 的 voice-call 插件配置中，将 provider 指向本地 Bridge：

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
            apiBaseUrl: "http://127.0.0.1:8080"
          },
          publicUrl: "http://127.0.0.1:8080/voice/webhook",
          streaming: {
            enabled: true,
            streamPath: "/voice/stream"
          }
        }
      }
    }
  }
}
```

## 硬件后端

### USB Voice Modem（推荐）

```env
BRIDGE_BACKEND=usb_modem
MODEM_PORT=COM3
MODEM_BAUD_RATE=115200
```

接线：电话线 (RJ11) → USB Voice Modem → PC USB

### Android 手机

```env
BRIDGE_BACKEND=android
ANDROID_DEVICE_ID=  # 可选，自动检测
```

接线：Android (USB + ADB) + 外接声卡 + 3.5mm 音频线

## 项目结构

```
src/
├── server.py                  # 主入口
├── config.py                  # 配置管理
├── bridge_manager.py          # 通话流程调度器
├── twilio_compat/             # Twilio 兼容 REST API
│   ├── rest_api.py            # POST /Calls.json
│   ├── twiml_parser.py        # 解析 TwiML <Stream>
│   └── webhook.py             # Webhook 回调
├── media_stream/              # WebSocket 媒体流
│   ├── ws_client.py           # WebSocket 客户端
│   ├── codec.py               # PCM/mulaw 编解码
│   └── protocol.py            # 消息类型定义
├── backends/                  # 硬件后端
│   ├── base.py                # 抽象接口
│   ├── usb_modem.py           # USB Voice Modem
│   ├── android.py             # ADB + scrcpy
│   └── mock.py                # 测试用 Mock
├── recording/                 # 双向录音
│   ├── recorder.py            # PCM 录制 + WAV 输出
│   └── storage.py             # 文件管理
├── db/
│   └── models.py              # SQLite 数据模型
└── web/                       # Web 管理后台
    ├── api.py                 # REST API
    └── static/                # 前端
        ├── index.html         # 控制台面板
        ├── records.html       # 通话记录
        ├── app.js             # 公共 JS
        └── style.css          # 样式
```

## 运行测试

```bash
python -m pytest tests/ -v
```

## License

MIT
