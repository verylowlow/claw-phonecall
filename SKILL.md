---
name: claw-phonecall
description: "使用OpenClaw通过ADB控制安卓手机完成电话呼出和语音交互。支持多并发通话，自动拨号、接听、挂断，集成火山引擎ASR/TTS实现智能对话。"
metadata:
  version: "0.1.0"
  author: "kinn @ OpenClaw"
  platform: "Android (rooted)"
read_when:
  - 控制安卓手机拨打电话
  - 实现自动语音对话
  - 多路电话并发控制
allowed-tools:
  - Bash
  - exec
---

# Claw Phone Call - 安卓电话控制技能

## 概述

通过OpenClaw控制安卓手机，使用ADB命令完成电话呼出、接听、挂断，并集成火山引擎ASR/TTS实现实时语音对话。

## 功能特性

- 📞 **电话控制**: 拨号、接听、挂断、DTMF按键
- 🎙️ **音频采集**: ALSA/FIFO管道，低延迟(~50ms)
- 🗣️ **语音识别**: 火山引擎ASR实时转写
- 🔊 **语音合成**: 火山引擎TTS流式播放
- 🔊 **VAD检测**: 语音活动检测，静音填充
- 📱 **多并发**: 支持多台手机同时通话

## 硬件要求

- 已Root的安卓手机
- USB数据线连接电脑
- 手机开启USB调试模式

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `configs/settings.yaml`：
```yaml
devices:
  - id: "phone1"
    serial: "ABCD123456"  # ADB设备序列号
    phone_number: "13511223344"

volcengine:
  asr:
    app_id: "6897139964"
    access_token: "your_token"
  tts:
    app_id: "6897139964"
    access_token: "your_token"
```

### 3. 使用

```python
from claw_phonecall import PhoneCall

# 初始化
phone = PhoneCall("ABCD123456")

# 拨打电话
phone.dial("13511223344")

# 等待对方接听
phone.wait_for_answer()

# 开始对话
phone.start_conversation(
    asr_config={...},
    tts_config={...},
    greeting="您好，我是AI助手，请问有什么可以帮您？"
)

# 挂断
phone.hangup()
```

## 项目结构

```
claw-phonecall/
├── SKILL.md              # 本文件
├── README.md              # 说明文档
├── requirements.txt       # Python依赖
├── configs/
│   └── settings.yaml     # 配置文件
├── scripts/
│   ├── __init__.py
│   ├── adb_control.py    # ADB手机控制
│   ├── audio_capture.py  # ALSA/FIFO音频采集
│   ├── vad.py            # 语音活动检测
│   ├── asr_client.py     # 火山ASR客户端
│   ├── tts_player.py     # 火山TTS播放器
│   ├── dialog_manager.py # 对话管理器
│   └── phone_call.py     # 主入口
└── tests/
    └── test_phone.py     # 测试
```

## 对话流程

```
开始
  ↓
拨号 → 等待接听
  ↓
对方接听 ← [检测通话状态]
  ↓
播放开场白 (TTS)
  ↓
循环:
  采集音频 → VAD检测 → ASR识别 → 大模型处理 → TTS播放
  ↓
检测结束关键词
  ↓
挂断 → 结束
```

## 配置说明

### ADB连接

```yaml
adb:
  # USB连接
  devices:
    - serial: "ABCD123456"  # 手机序列号
      name: "手机1"
  
  # 或WiFi连接 (需要先USB配置)
  # wifi:
  #   - ip: "192.168.1.100"
```

### 火山引擎配置

```yaml
volcengine:
  region: "cn-beijing"
  asr:
    app_id: "6897139964"
    access_token: "bsNydZqpKWMKuzLh-8BTVW25uVqyvqgU"
    resource_id: "volc.seedasr.auc"  # 模型2.0
  tts:
    app_id: "6897139964"
    access_token: "your_token"
    voice: "xiaoxiao"  # 默认音色
```

### 对话配置

```yaml
dialog:
  # 开场白
  greeting: "您好，我是AI助手，请问有什么可以帮您？"
  
  # 静音填充语
  silence_phrases:
    - "嗯嗯，请讲"
    - "好的，我在听"
  
  # 结束关键词
  end_keywords:
    - "再见"
    - "挂了吧"
    - "谢谢"
  
  # 最大对话轮次
  max_turns: 20
```

## 多并发示例

```python
from claw_phonecall import PhoneCallManager

# 创建管理器
manager = PhoneCallManager()

# 添加多台手机
manager.add_device("phone1", "ABCD123456", "13511111111")
manager.add_device("phone2", "EFGH789012", "13522222222")

# 同时拨打
results = manager.dial_all([
    ("phone1", "13800138000"),
    ("phone2", "13900139000")
])

# 同时开始对话
for device_id, result in results.items():
    if result["success"]:
        manager.start_conversation(device_id, greeting="您好")
```

## 常见问题

### Q: 音频延迟多少？
A: 约50ms（ALSA/FIFO方案）

### Q: 需要 root 权限吗？
A: 是的，需要root来访问ALSA音频设备

### Q: 支持哪些手机？
A: 所有已Root的安卓手机，推荐小米/一加/realme

### Q: 如何测试？
A: 1. 连接手机 2. 运行 python scripts/test_phone.py

## 注意事项

1. 确保手机已开启USB调试模式
2. 首次使用需要允许电脑调试
3. 通话会产生运营商资费
4. 建议使用耳机避免回声

## 技术支持

- GitHub: https://github.com/verylowlow/claw-phonecall
- Issues: https://github.com/verylowlow/claw-phonecall/issues