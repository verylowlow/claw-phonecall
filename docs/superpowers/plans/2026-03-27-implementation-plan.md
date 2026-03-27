# AI 电话 Agent 实现计划

**日期**: 2026-03-27
**状态**: 进行中
**基于**: 2026-03-27-phone-call-skill-design.md

---

## 1. 当前代码状态

### 已有的模块 (src/)
- `phone_controller.py` - 电话控制
- `audio_capture.py` - 音频捕获
- `audio_player.py` - 音频播放
- `ai_pipeline.py` - AI 管道 (VAD/ASR/TTS/LLM)
- `humanization.py` - 拟人化
- `config.py` - 配置
- `cli.py` - CLI 入口

### 设计文档已定义的模块
- `vad.py` - VAD 管理 (已在 ai_pipeline.py:52-117)
- `asr.py` - ASR 管理 (已在 ai_pipeline.py:119-183)
- `tts.py` - TTS 管理 (已在 ai_pipeline.py:185-275)
- `audio_buffer.py` - 语音段累积 (需要新增)
- `filler_cache.py` - 填充词缓存 (需要新增)
- `call_record.py` - 通话记录 (需要新增)
- `http_api.py` - HTTP API (需要新增)
- `phone_skill.py` - Skill 主程序 (需要新增)

---

## 2. 实现任务清单

### 阶段 1: 修复 P0 问题 (优先级最高)

#### 1.1 移除 LLMClient 纯占位代码
- **位置**: `ai_pipeline.py:277-332`
- **问题**: LLMClient 是纯占位实现
- **方案**: LLM 逻辑移至 OpenClaw 端，Python Skill 只负责硬件抽象
- **行动**:
  - [ ] 删除 LLMClient 类
  - [ ] 修改 AIPipeline，不包含 LLM 调用
  - [ ] 通过事件流将 ASR 结果发送给 OpenClaw Agent

#### 1.2 改造为事件流架构
- **问题**: ASR→LLM→TTS 闭环断裂
- **方案**: 使用 Python Generator 实现事件流
- **行动**:
  - [ ] 创建 `phone_skill.py` 主程序
  - [ ] 实现 `phone_call()` 生成器函数
  - [ ] 定义事件流格式 (status/user_speaking/agent_responding)

---

### 阶段 2: 新增核心模块

#### 2.1 实现 AudioBuffer (语音段累积)
- **位置**: `src/audio_buffer.py` (新增)
- **职责**: 累积完整语音段，等待 VAD 检测到静音段后送 ASR
- **接口**:
  ```python
  class AudioBuffer:
      def __init__(self, max_duration_ms: int = 10000)
      def add(self, audio_chunk: bytes) -> None
      def is_complete(self, vad_result) -> bool
      def get_audio() -> bytes
      def clear() -> None
      def has_content() -> bool
  ```

#### 2.2 实现 FillerCache (填充词缓存)
- **位置**: `src/filler_cache.py` (新增)
- **职责**: 启动时预合成填充词音频，运行时直接使用缓存
- **接口**:
  ```python
  class FillerCache:
      def __init__(self, tts_manager)
      async def preload(self, filler_phrases: List[str]) -> None
      def get(self, text: str) -> Optional[bytes]
  ```

#### 2.3 实现 CallRecord (通话记录)
- **位置**: `src/call_record.py` (新增)
- **职责**: 存储通话记录到 SQLite
- **数据库**: `call_records.db`
- **接口**:
  ```python
  @dataclass
  class CallRecordData:
      id: Optional[int]
      phone_number: str
      call_time: datetime
      duration: int
      call_type: str  # 'inbound' / 'outbound'
      user_text: str
      agent_response: str

  class CallRecord:
      def __init__(self, db_path: str = "call_records.db")
      def save(self, record: CallRecordData) -> int
      def get_by_phone(self, phone_number: str) -> List[CallRecordData]
      def get_by_id(self, record_id: int) -> Optional[CallRecordData]
      def get_all(self, limit: int = 100, offset: int = 0) -> List[CallRecordData]
  ```

#### 2.4 实现 HTTPServer (HTTP API)
- **位置**: `src/http_api.py` (新增)
- **接口**:
  ```python
  class HTTPServer:
      def __init__(self, host: str = "0.0.0.0", port: int = 8080)
      def register_call_record(self, call_record: CallRecord)
      def start()
      def stop()
  ```
- **端点**:
  - `GET /api/calls` - 列出所有通话记录
  - `GET /api/calls?phone=xxx` - 按手机号查询
  - `GET /api/calls/{id}` - 查看单条记录
  - `GET /health` - 健康检查

---

### 阶段 3: 改造 phone_skill.py (事件流主程序)

#### 3.1 创建 phone_skill.py
- **位置**: `src/phone_skill.py` (新增)
- **职责**: 作为 OpenClaw Tool 长期运行的事件流程序

#### 3.2 外呼流程
```python
def phone_call(phone_number: str):
    # 1. 状态: dialing
    yield {"event": "status", "status": "dialing", "phone": phone_number}

    # 2. 拨号
    phone_controller.dial(phone_number)

    # 3. 状态: connecting
    yield {"event": "status", "status": "connecting"}

    # 4. 等待接听
    phone_controller.wait_for_state(CallState.OFFHOOK)

    # 5. 状态: call_started
    yield {"event": "status", "status": "call_started"}

    # 6. 通话循环
    while True:
        audio_chunk = audio_capture.read()

        vad_result = vad.detect(audio_chunk)
        audio_buffer.add(audio_chunk)

        if vad_result.has_silence_after_speech and audio_buffer.has_content:
            # ASR 转写
            user_text = asr.transcribe(audio_buffer.get_audio())
            audio_buffer.clear()

            # 返回给 OpenClaw Agent
            yield {"event": "user_speaking", "text": user_text}

            # 等待 Agent 回复 (通过 Tool 返回值)
            # 继续执行...

            # TTS 播放
            for chunk in tts.synthesize(agent_response):
                audio_player.play(chunk)

            yield {"event": "agent_responding", "text": agent_response}

        if phone_controller.get_call_state() == CallState.IDLE:
            yield {"event": "status", "status": "ended"}
            break
```

---

### 阶段 4: 更新 Skill 定义

#### 4.1 更新 SKILL.md
- **位置**: `skills/phone_call/SKILL.md`
- **行动**:
  - [ ] 更新调用方式为事件流
  - [ ] 说明 OpenClaw Agent 交互方式
  - [ ] 添加 HTTP API 文档

---

## 3. 实现顺序 (优先级排序)

| # | 任务 | 依赖 | 状态 |
|---|------|------|------|
| 1 | 删除 LLMClient，占位代码 | - | ⏳ 待开始 |
| 2 | 创建 audio_buffer.py | - | ⏳ 待开始 |
| 3 | 创建 filler_cache.py | TTSManager | ⏳ 待开始 |
| 4 | 创建 call_record.py | - | ⏳ 待开始 |
| 5 | 创建 http_api.py | CallRecord | ⏳ 待开始 |
| 6 | 创建 phone_skill.py (事件流) | 上述所有 | ⏳ 待开始 |
| 7 | 更新 SKILL.md | phone_skill.py | ⏳ 待开始 |

---

## 4. 待确定问题 (需要决策)

### 4.1 Agent 回复传递方式
- **已确定**: 使用 OpenClaw Tool 返回值机制
- **流程**:
  1. Python Skill yield `user_speaking` 事件 → OpenClaw 等待
  2. OpenClaw Agent 处理完 → Tool 返回 Agent 回复
  3. Python Skill 收到回复 → 继续执行 TTS

### 4.2 Skill 部署方式
- **选择**: 方案 A (bash 调用 Python 脚本)
- **实现**: 通过 bash 工具调用 `python src/phone_skill.py`

### 4.3 实时性考虑
- **风险**: OpenClaw Tool 等待可能影响实时性
- **方案**: 后续根据实际测试调整

---

## 5. 文件清单

```
src/
├── __init__.py                 (已有)
├── config.py                   (已有)
├── phone_controller.py         (已有)
├── audio_capture.py            (已有)
├── audio_player.py             (已有)
├── vad.py                      (拆分 from ai_pipeline.py)
├── asr.py                      (拆分 from ai_pipeline.py)
├── tts.py                      (拆分 from ai_pipeline.py)
├── audio_buffer.py             (新增)
├── filler_cache.py             (新增)
├── call_record.py              (新增)
├── http_api.py                 (新增)
├── phone_skill.py              (新增)
├── ai_pipeline.py              (修改: 删除 LLMClient)
├── humanization.py             (已有，可能需要调整)
└── cli.py                      (已有)
```

---

## 6. 验收标准

- [ ] `phone_call("138xxx")` 能发起外呼
- [ ] 用户说话后 ASR 转写文本返回给 Agent
- [ ] Agent 回复通过 TTS 播放
- [ ] 通话结束后通话记录保存到 SQLite
- [ ] HTTP API 可以查询通话记录

---

**计划版本**: 1.0
**下一步**: 开始阶段1 - 移除 LLMClient 占位代码