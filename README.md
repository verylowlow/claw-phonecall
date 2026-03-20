# Claw Phone Call

通过 OpenClaw 控制安卓手机完成电话呼出和语音交互。

## 功能特性

- 📞 电话控制：拨号、接听、挂断、DTMF
- 🎙️ 低延迟音频采集：ALSA/FIFO 方案 ~50ms
- 🗣️ 语音识别：火山引擎 ASR 实时转写
- 🔊 语音合成：火山引擎 TTS 流式播放
- 🔊 VAD 检测：语音活动检测，静音填充
- 📱 多并发：支持多台手机同时通话

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `configs/settings.yaml`，设置：
- ADB 设备序列号
- 火山引擎 ASR/TTS 配置
- 对话参数

### 3. 使用

```python
from scripts.phone_call import PhoneCall

# 创建电话控制实例
phone = PhoneCall("设备序列号")

# 拨打并开始对话
phone.run_full_call("13800138000", "您好，请问有什么可以帮您？")
```

或使用命令行：

```bash
# 列出设备
python scripts/phone_call.py list

# 拨打电话
python scripts/phone_call.py -s ABCD123456 dial 13800138000

# 获取设备信息
python scripts/phone_call.py -s ABCD123456 info
```

## 硬件要求

- 已 Root 的安卓手机
- USB 数据线连接电脑
- 手机开启 USB 调试模式

## 项目结构

```
claw-phonecall/
├── SKILL.md                 # 技能定义
├── README.md                # 说明文档
├── requirements.txt        # Python 依赖
├── configs/
│   └── settings.yaml       # 配置文件
└── scripts/
    ├── __init__.py
    ├── adb_control.py       # ADB 手机控制
    ├── audio_capture.py    # 音频采集
    ├── vad.py              # 语音活动检测
    ├── asr_client.py       # 火山 ASR
    ├── tts_player.py       # 火山 TTS
    ├── dialog_manager.py   # 对话管理
    └── phone_call.py       # 主入口
```

## 技术方案

详见 [SKILL.md](./SKILL.md)

## GitHub

https://github.com/verylowlow/claw-phonecall