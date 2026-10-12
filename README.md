# Claw Phone Call

**让 AI Agent 用你手边的安卓手机打电话。** 不买VoIP 服务、不申请号码、不接 SIP 中继线—— 一台已 Root 的安卓手机 + 一条 USB 线，就是一部能被 Agent 调用的电话。

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![OpenClaw](https://img.shields.io/badge/skill-OpenClaw-purple.svg)](SKILL.md)
[![License](https://img.shields.io/badge/license-source--available-informational.svg)](#license)

> English version: [README_EN.md](README_EN.md)

> **想直接听效果？拨打 165-1124-4888** —— 真人接听，AI 应答，通话按普通话费计费。

---

## 为什么是"手边的手机"

做 AI 电话外呼，市面上的方案无非三类，各自都有让人难受的地方：

| 方案 | 痛点 |
|------|------|
| 云端 AI 外呼 SaaS | 号码被标记率高接通率差；通话数据在别人服务器；按分钟持续付费 |
| SIP 中继 / VoIP 号码 | 要营业执照、要开户；虚拟号容易被判定为营销号；配置复杂 |
| 买一台语音网关 | 硬件之外还要折腾 SIP 栈与驱动 |

**本项目的路子：直接用你已有的手机。** 手机本身就是一部标准电话，插上 SIM 卡就能打，
用的是真实手机号、真实 SIM 的通话质量，不需要任何服务商的账户或审批。

配合 OpenClaw 的 Agent 能力，Agent 就可以像调用别的工具一样调用这部手机。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 📞 **电话控制** | 拨号、接听、挂断、DTMF 按键、通话状态检测 |
| 🎙️ **低延迟音频采集** | ALSA + FIFO 管道方案，音频侧延迟约 **50ms** |
| 🗣️ **实时语音识别** | 火山引擎 SeedASR 流式转写（需自备 app_id / token） |
| 🔊 **语音合成** | **EdgeTTS**（微软 Edge 引擎，**免费且无需密钥**） |
| 🔊 **VAD 语音活动检测** | 自动区分说话与静音，支持静音填充话术 |
| 📱 **多机并发** | 多台手机同时通话，统一编排 |
| 🛠️ **完整设备控制** | 点击、滑动、Home / 电源键、文本输入、截屏、启停应用 |

### 对话链路

```
Agent 下指令 → 拨号 → 等待接听 → 播放开场白
   ↓
┌─ 循环 ──────────────────────────────┐
│ 采集音频 → VAD 判定说话 → ASR 转写  │
│     → 大模型处理 → TTS 合成 → 播放  │
└─────────────────────────────────────┘
   ↓
命中结束关键词 / 达到轮次上限 → 挂断
```

---

## 硬件要求

- **已 Root 的安卓手机**（需要 root 才能访问 ALSA 音频设备）
- USB 数据线 + 开启 USB 调试模式
- 电脑端 Python 3.9+

推荐机型：小米 / 一加 / realme 等 root 社区活跃的机型。

> **为什么需要 root**：本项目的音频通路走手机本机的 ALSA 设备 + FIFO 管道，
> 这是能做到 ~50ms 延迟的关键，未 root 的设备无法建立这条通路。

---

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/verylowlow/claw-phonecall.git
cd claw-phonecall
pip install -r requirements.txt
```

### 2. 配置

编辑 `configs/settings.yaml`：

```yaml
adb:
  mode: usb                # usb 或 wifi
  devices:
    - id: "phone1"
      serial: "ABCD123456789"    # adb devices 看到的序列号
      name: "测试手机1"
      phone_number: "13511223344"

volcengine:
  region: cn-beijing
  asr:
    app_id: "你的 app_id"
    access_token: "你的 access_token"
    resource_id: "volc.seedasr.auc"   # SeedASR 模型 2.0
```

> 🔒 **关于凭据**：TTS 走 EdgeTTS，**不需要任何密钥**；只有 ASR 需要火山引擎凭据。
> 请**不要把真实 token 提交进仓库** —— 示例配置填占位符即可，
> 你的真实配置建议放在本地未提交的文件中，或通过环境变量注入。

### 3. 确认设备已连上

```bash
adb devices# 确认手机状态为 device 而非 unauthorized
python scripts/phone_call.py list
```

### 4. 使用

**Python 调用**

```python
from scripts.phone_call import PhoneCall

phone = PhoneCall("ABCD123456789")

# 一站式：拨号 → 等接听 → 对话 → 挂断
phone.run_full_call("13800138000", greeting="您好，我是AI助手，请问有什么可以帮您？")

# 或分步控制
phone.dial("13800138000")
if phone.wait_for_answer(timeout=30):
    phone.start_conversation()
    phone.hangup()
```

**命令行**

```bash
python scripts/phone_call.py list    # 列出已连设备
python scripts/phone_call.py -s ABCD123 info# 查看设备信息
python scripts/phone_call.py -s ABCD123 dial 13800138000   # 拨打并对话
```

**多机并发**

```python
from scripts.phone_call import PhoneCallManager

manager = PhoneCallManager()
manager.add_device("phone1", "ABCD123456", "13511111111")
manager.add_device("phone2", "EFGH789012", "13522222222")

# 同时拨号，等待接听
connected = manager.dial_and_connect([
    ("phone1", "13800138000"),
    ("phone2", "13900139000"),
])
```

**作为 OpenClaw Skill 使用**

仓库内的 [`SKILL.md`](SKILL.md) 是标准的 OpenClaw 技能定义，
声明了触发条件与允许的工具，可直接被 OpenClaw 加载。

---

## 项目结构

```
claw-phonecall/
├── SKILL.md                # OpenClaw 技能定义
├── README.md
├── requirements.txt
├── configs/
│   └── settings.yaml       # 设备与 ASR/TTS 配置
└── scripts/
    ├── adb_control.py      # ADB 设备控制（拨号/按键/点击/截屏）
    ├── audio_capture.py    # ALSA + FIFO 音频采集与播放
    ├── vad.py              # 语音活动检测 + 静音填充
    ├── asr_client.py       # 火山引擎 SeedASR 客户端
    ├── tts_player.py       # EdgeTTS 播放器
    ├── dialog_manager.py   # 对话状态机与多路编排
    └── phone_call.py       # 主入口 / CLI
```

---

## 常见问题

**Q：延迟有多少？**
音频侧约 50ms（ALSA + FIFO）。端到端还取决于 ASR / TTS 的网络往返。

**Q：必须 root 吗？**
是。访问 ALSA 音频设备需要 root，这是低延迟方案的前提。

**Q：支持哪些手机？**
所有已 root 的安卓机型，建议选 root 社区活跃、屏幕常亮策略可配置的机型。

**Q：能同时打几通？**
取决于你挂了几台手机。每台手机作为一个独立设备注册进 `devices` 列表。

**Q：会不会算骚扰电话？**
请只拨你有合法业务关系的号码（订单通知、服务回访等）。
陌生号码批量外呼违反通信法规，本项目不提供也不支持此类用途。

---

## 安全提醒

- 本项目会**操作你的真实手机**：拨号、点击、启停应用。**运行前请确认设备配置无误。**
- 通话会产生运营商话费。
- 建议使用耳机，避免回声被麦克风采集造成 AI 自问自答。
- **请勿将真实凭据（app_id / access_token / 设备序列号）提交到公开仓库。**

---

## ⭐ Star 支持

如果这个项目帮你省下了一套 VoIP 服务和一堆配置，随手点个 **Star** ⭐，让更多需要它的人看到。

<p align="center">
  <b>需要能接打真实固话 / 400 号码的完整一体机方案？</b><br>
  AI 电话客服整机（本地部署 · 私有化 · 断网可用）已在生产环境运行，<br>
  欢迎拨打体验热线 <b>165-1124-4888</b> 直接听 AI 接听效果。
</p>

---

## License

本项目源码可自由阅读、修改与自部署。**商业分发与二次销售需获得授权。**
LICENSE 文件待补充，在此之前请勿假设任何授权条款。