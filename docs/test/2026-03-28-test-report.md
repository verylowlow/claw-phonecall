# AI 电话 Agent 测试报告

**测试日期**: 2026-03-28
**测试人员**: Claude
**设备**: Xiaomi MI 5 (Android 15)
**ADB 设备 ID**: 41439f84

---

## 🔴 硬件问题 (阻塞测试)

**3.5mm 耳机连接问题**: 手机无法识别插入的耳机，需要解决后才能继续测试音频下行。

---

## 测试结果摘要

| 模块 | 功能 | 状态 | 备注 |
|------|------|------|------|
| PhoneController | 拨号 | ✅ | 使用 ACTION_CALL |
| PhoneController | 挂断 | ✅ | input keyevent 6 |
| PhoneController | 接听 | ✅ | input keyevent 5 |
| PhoneController | 状态获取 | ✅ | dumpsys telephony.registry |
| PhoneController | 状态监控 | ✅ | 后台线程 |
| AudioPlayer | 音频播放 | ✅ | PyAudio 正常工作 |
| AudioCapture | 音频上行捕获 | ✅ | scrcpy voice-performance |
| AudioCapture | 音频上行 (通话) | ✅ | 录音成功 262KB |
| AudioPlayer | 音频下行 | 🔴 | 待解决 3.5mm 连接问题，使用扬声器替代测试通过 |
| TTS | 语音合成 | ✅ | Edge-TTS，已修复格式问题 |
| Humanization | 填充词 | ✅ | 4个填充词 |
| CallRecord | 通话记录 | ✅ | SQLite 存储 |
| HTTP API | REST API | ✅ | 正常响应 |

---

## 1. 集成测试 (test_integration.py)

**结果**: 6/6 通过 ✅

```
- Config Loading: PASS
- PhoneController Init: PASS
- AudioCapture Init: PASS
- AudioPlayer Init: PASS
- Humanization Init: PASS
- AIPipeline Init: PASS
```

---

## 2. 音频捕获关键发现 (scrcpy)

### 2.1 audio-source 选项

| 音频源 | 用途 | 测试结果 |
|--------|------|----------|
| `output` | 捕获扬声器输出 | ✅ 音乐播放时有效 |
| `voice-performance` | 捕获通话音频 | ✅ 推荐用于通话场景 |
| `playback` | 捕获应用音频 | ❌ 无效 |
| `mic` | 捕获麦克风 | 未测试 |

### 2.2 关键配置

**代码已更新** (`config.py`):
```python
SCRCPY_CONFIG = {
    "audio_source": "voice-performance",  # 通话场景推荐
    "audio_codec": "opus",
    "audio_bit_rate": 128000,
}
```

### 2.3 测试命令示例
```bash
# 捕获通话音频
scrcpy --no-video --no-control --audio-source=voice-performance --audio-codec=opus

# 捕获扬声器输出
scrcpy --no-video --no-control --audio-source=output --audio-codec=opus
```

---

## 3. 电话控制功能测试

### 2.1 拨号测试

**测试号码**: 18510339125

**结果**: ✅ 成功

**实现方式**:
1. 优先使用 `am start -a android.intent.action.CALL tel:{number}`
2. 备选使用 `am start -a android.intent.action.DIAL` + `input keyevent 5`

**关键发现**:
- `service call phone 1` 在 Android 15 上无效（返回成功但未实际拨号）
- `ACTION_CALL` 可以直接发起呼叫
- 需要设置 SELinux 为 Permissive: `setenforce 0`

### 2.2 挂断测试

**命令**: `input keyevent 6`
**结果**: ✅ 成功

### 2.3 接听测试

**命令**: `input keyevent 5`
**结果**: ✅ 成功

### 2.4 状态监控测试

**测试**: 启动后台监控线程，监控 15 秒

**结果**: ✅ 成功
- 状态变化回调正常工作
- 检测到 IDLE 状态

---

## 3. 音频模块测试

### 3.1 音频播放 (AudioPlayer)

**结果**: ✅ 成功

**测试方法**: 播放 440Hz 正弦波 1 秒

**可用输出设备**:
- Microsoft 音频映射器 - Output
- 立体声混音 (2- USB Audio Device) - 设备索引 4
- 蓝牙耳机 (Audio Device)
- Senary Audio Output 1/2
- 等等

### 3.2 音频捕获 (AudioCapture)

**状态**: ✅ 已完成

**测试结果**:
- 音乐播放时捕获: ✅ 成功 (262KB)
- 通话中捕获 (voice-performance): ✅ 成功 (262KB)
- 通话中捕获 (output): ❌ 无效 (44 bytes)
- 通话中捕获 (playback): ❌ 无效 (44 bytes)

**结论**: 使用 `--audio-source=voice-performance` 捕获通话音频

---

## 4. 其他模块测试

### 4.1 Humanization

**结果**: ✅ 成功

- 填充词数量: 4
- 填充词列表: ['嗯', '好的', '让我想想', '这个']

### 4.2 CallRecord

**结果**: ✅ 成功

- SQLite 数据库创建正常
- 记录保存/查询正常

### 4.3 HTTP API

**结果**: ✅ 成功

- GET /api/calls: 200
- GET /health: 200

---

## 5. 代码修复记录

### 5.1 ADB 权限问题

**问题**: 普通 shell 没有 input 命令权限

**修复**:
- 在 `phone_controller.py` 中添加 `use_root` 参数
- 需要 root 权限的命令先尝试普通方式，失败再尝试 `su -c`

### 5.2 拨号方式问题

**问题**: `service call phone 1` 在 Android 15 上无效

**修复**:
- 优先使用 `ACTION_CALL` intent
- 备选使用 `ACTION_DIAL` + 按键模拟

---

## 6. 待测试项目

### 6.1 音频捕获 (AudioCapture) ✅ 已完成

- scrcpy 音频捕获: ✅ 使用 voice-performance
- 通话中音频捕获: ✅ 成功

### 6.2 音频上行 (2026-03-29 更新) ✅

**关键发现**: scrcpy 启动顺序很重要！

- ✅ **先启动 scrcpy，再拨号** = 成功捕获 262KB
- ❌ 先拨号，再启动 scrcpy = 失败 (44 bytes)

**原因**: scrcpy 需要在通话建立之前启动才能捕获音频流

**代码更新**: 需要在 `phone_skill.py` 中调整启动顺序

### 6.3 音频下行 🔴 阻塞

**问题**: 3.5mm 耳机插入手机后无法识别

**临时方案**: 使用电脑扬声器播放，你直接用耳朵听（已验证 TTS 正常）

**需要解决**:
- 检查手机 3.5mm 接口是否损坏
- 尝试其他 3.5mm 音频线
- 检查 USB 外接声卡是否正常工作

### 6.3 ASR/TTS

需要完成:
- 配置 ASR 服务 (Whisper)
- 配置 TTS 服务
- 端到端语音对话测试

### 6.4 火山引擎 ASR 集成 (2026-03-29) ✅

**新增文件**: `src/volc_asr.py`

**配置** (`config.py`):
```python
ASR_CONFIG = {
    "provider": "volcengine",  # 默认使用火山引擎
}

VOLC_ASR_CONFIG = {
    "app_key": "6897139964",
    "access_token": "bsNydZqpKWMKuzLh-8BTVW25uVqyvqgU",
    "secret_key": "KciLAGyqNwPeYMa1FhBHaXFwly9-4xYf",
}
```

**功能**:
- WebSocket 流式 ASR
- 实时返回识别结果
- 支持中文、英文等多种语言

### 6.5 OpenClaw 集成

需要完成:
- phone_skill 与 OpenClaw 集成
- 事件流完整测试

---

## 7. 代码修复

### 7.1 TTS 格式修复 (2026-03-29)

**问题**: edge-tts 输出 MP3 格式，但代码中错误使用 `-f webm`

**修复** (`ai_pipeline.py`):
```python
# 修复前
"-f", "webm", "-acodec", "opus", "-i", "pipe:0"

# 修复后
"-f", "mp3", "-acodec", "mp3float", "-i", "pipe:0"
```

### 7.2 scrcpy audio_source 配置 (2026-03-28)

**添加** (`config.py`):
```python
SCRCPY_CONFIG = {
    "audio_source": "voice-performance",  # 通话场景推荐
    ...
}
```

## 8. 测试环境

- Python: 3.13.3
- scrcpy: 3.3.3
- Android: 15 (API 35)
- 设备: Xiaomi MI 5
- ADB: 已获取 root 权限
- SELinux: Permissive