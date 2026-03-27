# AI Phone Agent

基于 Openclaw 的智能电话 Agent，使用真实安卓手机实现 AI 外呼/接听功能。

## 方案概述

采用**方案 C（混合优化）**：
- **上行（手机 → PC）**：scrcpy 数字音频捕获
- **下行（PC → 手机）**：物理声卡输出
- **控制**：ADB 指令

## 项目结构

```
agentcalls/
├── src/
│   ├── __init__.py       # 模块入口
│   ├── config.py         # 配置管理
│   ├── phone_controller.py   # 手机通话控制
│   ├── audio_capture.py      # 音频捕获 (scrcpy)
│   ├── audio_player.py       # 音频播放 (PyAudio)
│   ├── humanization.py      # 拟人化策略
│   └── ai_pipeline.py       # AI 处理管道
├── tests/
│   └── test_integration.py # 集成测试
├── docs/
│   └── plans/            # 设计文档
├── requirements.txt      # 依赖
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备环境

- 安装 [scrcpy](https://github.com/Genymobile/scrcpy)
- 安装 [ffmpeg](https://ffmpeg.org/)
- 准备已 Root 的安卓手机（方案 C 不强求 Root，但 ADB 控制需要）

### 3. 运行测试

```bash
python tests/test_integration.py
```

## 使用示例

```python
from src import PhoneController, AudioCapture, AudioPlayer, AIPipeline

# 初始化
phone = PhoneController()
capture = AudioCapture()
player = AudioPlayer()

# 创建 AI 管道
pipeline = AIPipeline(phone)
pipeline.set_audio_devices(capture, player)
pipeline.load_models()

# 发起外呼
import asyncio
asyncio.run(pipeline.start_outbound_call("13800138000"))

# 或处理来电
phone.start_monitoring(
    on_incoming=lambda e: asyncio.run(pipeline.handle_incoming_call(e))
)
```

## 配置

编辑 `src/config.py`：

```python
# 音频配置
AUDIO_CONFIG = {
    "sample_rate": 16000,
    "channels": 1,
}

# TTS 配置
TTS_CONFIG = {
    "voice": "zh-CN-XiaoxiaoNeural",
}
```

## 硬件要求

- USB 外置声卡 (CM108)
- 3.5mm 对录线
- 已 Root 的安卓手机（建议）

## 许可证

MIT License