# AI 电话 Agent 项目设计文档

## 1. 项目概述

**项目名称**: AI Phone Agent  
**项目目标**: 基于 Openclaw + Root 安卓手机，实现纯软件控制的 AI 外呼/接听机器人  
**核心方案**: 方案 C（混合优化）- 上行 scrcpy 数字捕获 + 下行物理声卡链路

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PC 端 (Openclaw)                                │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │   VAD 检测   │ → │  ASR 语音识别 │ → │ LLM 大语言模型 │ → │ TTS 语音合成│ │
│  │  (Silero)    │   │ (Faster-Whisper)│  │  (Openclaw)  │   │ (Edge-TTS)  │ │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬────────┘ │
│         │                  │                  │                  │          │
│  ┌──────┴──────────────────┴──────────────────┴──────────────────┴────────┐ │
│  │                           音频路由层 (Python)                             │ │
│  │   ┌─────────────────┐                    ┌─────────────────────────┐ │ │
│  │   │ scrcpy 音频捕获 │ ← 上行 (手机→PC)    │ 虚拟声卡/VB-Audio Cable │ │ │
│  │   │ (手机系统音频)  │                    │ ← 物理声卡输出 (PC→手机)│ │ │
│  │   └─────────────────┘                    └─────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ ADB 控制指令
                                      ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                          安卓手机 (Root + USB)                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────────┐ │
│  │  通话控制    │   │  音频播放     │   │  麦克风输入                       │ │
│  │ (ADB Shell)  │   │ (手机扬声器)  │   │ (物理连接: 声卡→对录线→手机)    │ │
│  └──────────────┘   └──────────────┘   └──────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 音频路径设计

| 方向 | 实现方式 | 技术选型 |
|---|---|---|
| **上行 (手机 → PC)** | scrcpy 音频捕获 | scrcpy --audio-codec=opus → ffmpeg 重采样 → 虚拟声卡 |
| **下行 (PC → 手机)** | 物理声卡输出 | USB 外置声卡 (CM108) → 3.5mm 对录线 → 手机麦克风 |
| **控制** | ADB 指令 | input keyevent 5/6, dumpsys, logcat |

---

## 3. 功能模块设计

### 3.1 模块 1: 手机通话控制 (PhoneController)

**职责**: 通过 ADB 控制手机的拨号、接听、挂断、状态监控

```python
class PhoneController:
    def __init__(self, device_id: str = None):
        self.device_id = device_id  # 多手机时指定设备
    
    def get_call_state(self) -> int:
        """获取通话状态: 0=IDLE, 1=RINGING, 2=OFFHOOK"""
        
    def dial(self, phone_number: str):
        """拨打电话"""
        
    def answer(self):
        """接听电话 (模拟按键 EVENT 5)"""
        
    def hangup(self):
        """挂断电话 (模拟按键 EVENT 6)"""
        
    def start_monitoring(self, callback: callable):
        """后台监控通话状态变化"""
```

### 3.2 模块 2: 音频捕获 (AudioCapture)

**职责**: 从 scrcpy 捕获手机音频流，处理后供 ASR 使用

```python
class AudioCapture:
    def __init__(self, device_id: str = None):
        self.scrcpy_process = None
        
    def start_capture(self) -> None:
        """启动 scrcpy 音频捕获"""
        
    def get_audio_stream(self) -> Generator[bytes]:
        """返回原始音频流"""
        
    def stop_capture(self) -> None:
        """停止捕获"""
```

### 3.3 模块 3: 音频播放 (AudioPlayer)

**职责**: 将 TTS 音频通过物理声卡输出到手机

```python
class AudioPlayer:
    def __init__(self, output_device: str = None):
        self.stream = None
        
    def play(self, audio_data: bytes) -> None:
        """播放音频 (PyAudio)"""
        
    def play_stream(self, audio_stream: Generator[bytes]) -> None:
        """流式播放"""
```

### 3.4 模块 4: AI 管道 ( AIPipeline )

**职责**: 整合 VAD + ASR + LLM + TTS，实现拟人化对话

```python
class AIPipeline:
    def __init__(self, phone_controller: PhoneController):
        self.vad = SileroVAD()
        self.asr = FasterWhisperASR()
        self.llm = OpenclawLLM()  # 复用 Openclaw
        self.tts = EdgeTTS()
        
    async def start_call(self, phone_number: str):
        """启动外呼流程"""
        
    async def handle_incoming(self):
        """处理呼入电话"""
        
    async def process_audio(self, audio_chunk: bytes):
        """处理实时音频流"""
        
    def set_on_response(self, callback: callable):
        """设置响应回调"""
```

### 3.5 模块 5: 拟人化策略 (Humanization)

**职责**: 填充词、打断处理、静音检测

```python
class Humanization:
    def __init__(self):
        self.filler_phrases = ["嗯", "好的", "我在听", "明白"]
        
    def should_insert_filler(self, silence_duration: float) -> bool:
        """判断是否插入填充词"""
        
    def handle_barge_in(self) -> None:
        """处理用户打断"""
```

---

## 4. 核心流程设计

### 4.1 外呼流程 (Outbound Call)

```
1. 用户触发外呼 → PhoneController.dial(号码)
2. 等待对方接听 (mCallState=2)
3. 接通后 → AudioPlayer 播放欢迎语 ("喂，您好")
4. 启动 VAD 监听 → 检测用户说话
5. 用户说话结束 → ASR 转写 → LLM 生成回复
6. TTS 合成 → AudioPlayer 播放
7. 循环 4-7 直到对方挂断
8. 检测到挂断 → 释放资源，回到 IDLE
```

### 4.2 呼入流程 (Inbound Call)

```
1. PhoneController 后台监控 mCallState
2. 检测到 RINGING (mCallState=1)
3. 等待 2-3 秒 → PhoneController.answer()
4. 接通后 → 同外呼流程步骤 3-8
```

---

## 5. 技术栈

| 组件 | 技术选型 | 版本 |
|---|---|---|
| Python | 3.10+ | 核心语言 |
| ADB | adb-shell | Python 库 |
| 音频捕获 | scrcpy + ffmpeg | 2.0+ |
| 音频播放 | pyaudio | 0.2.14 |
| VAD | silero-vad | 最新 |
| ASR | faster-whisper | 0.10.0+ |
| TTS | edge-tts | 最新 |
| 虚拟声卡 | VB-Audio Cable | Windows |

---

## 6. 目录结构

```
D:\dev\agentcalls\
├── src/
│   ├── __init__.py
│   ├── phone_controller.py    # 手机控制模块
│   ├── audio_capture.py       # scrcpy 音频捕获
│   ├── audio_player.py        # 物理声卡播放
│   ├── ai_pipeline.py        # AI 处理管道
│   ├── humanization.py       # 拟人化策略
│   └── config.py              # 配置文件
├── tests/
│   ├── test_phone_controller.py
│   ├── test_audio_capture.py
│   ├── test_audio_player.py
│   └── test_ai_pipeline.py
├── docs/
│   └── plans/
│       └── 2026-03-26-ai-phone-agent-design.md
├── requirements.txt
└── README.md
```

---

## 7. 关键风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| scrcpy 音频捕获失败 | 上行链路不通 | 预留 logcat 音频捕获备选方案 |
| 物理声卡输出延迟 | 通话不自然 | 使用低延迟 buffer (256-512 frames) |
| 回声问题 | 对方听到回声 | 集成 WebRTC AEC 算法 |
| 多手机并发 | 资源冲突 | 每个手机独立进程+进程间通信 |
| ADB 连接断开 | 控制失效 | 添加重连机制和状态恢复 |

---

## 8. 待硬件测试的关键点

1. **scrcpy 音频延迟**: 实测是否满足 < 800ms
2. **物理链路音频质量**: 底噪是否可接受
3. **双向通话延迟**: 端到端延迟能否控制在 1.5s 内
4. **长时间稳定性**: 30 分钟通话是否出现音频偏移
5. **多手机并发**: 3 台手机同时运行是否稳定

---

**设计文档版本**: 1.0  
**创建时间**: 2026-03-26  
**状态**: 待用户审批