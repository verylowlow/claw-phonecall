# Contributing to AgentCallCenter

感谢参与。这个项目只做**传输层**（音频通路 + Twilio 兼容 + 硬件抽象），
不涉及 ASR / LLM / TTS —— 这条边界让仓库保持零商业依赖，也让它可以被放心复用。

## 开始之前

**大改动请先开 Issue 讨论。** 尤其是：
- 新增硬件后端（请说明模块型号、AT 口/音频口如何区分、音频格式）
- 改动 Twilio 兼容层（会影响现有集成）
- 改动音频格式或采样率

小修复（拼写、注释、明显的逻辑错误）可以直接提 PR。

## 开发环境

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

不需要真实硬件就能跑测试和开发：把 `BRIDGE_BACKEND=mock` 即可。

## 提交前必做

```bash
python -m pytest tests/ -v          # 测试必须全绿
python -m py_compile src/**/*.py    # 语法检查
git grep -niE "shitren|微信|weixin"  # 合规：不要带联系方式
```

## 代码风格

- 保持现有风格，不做大范围格式化（会让 diff 无法审阅）
- 类型注解：新增的公开函数请加
- 注释写**为什么**，不写**做了什么**

```python
# 好：解释这个窗口存在的原因
# ATD 是异步的：先回 OK（命令已接受），稍后才报 VOICE CALL: BEGIN。
_URC_DRAIN_S = 0.5

# 差：复述代码
# 等待 0.5 秒
```

## 写硬件后端

继承 `TelephonyBackend`，实现 6 个抽象方法即可：

```python
class MyBackend(TelephonyBackend):
    async def initialize(self) -> None: ...
    async def dial(self, number: str) -> bool: ...
    async def answer(self) -> bool: ...
    async def hangup(self) -> bool: ...
    async def read_audio(self, num_samples: int) -> bytes | None: ...
    async def write_audio(self, data: bytes) -> None: ...
```

**两条硬性要求：**

1. **失败必须如实上报。** `hangup()` 在 `ATH` 返回 `ERROR` 时返回 `False`，
   不要图省事返回 `True` —— 桥接层会以为已挂断，实际线路还占着，
   症状是"下一通拨不通"，极难排查。
2. **不要在 `__init__` 里访问硬件。** 只在 `initialize()` 里打开，
   构造对象应该永远不失败。

## 安全

不要提交任何真实凭据：SIP 密码、Twilio Token、阿里云 / 火山 AK。
用 `.env.example` 做模板。如果你发现仓库里已经有真实凭据，
**请直接提 Issue 私下告知**，不要在公开 Issue 里贴出来。

## License

贡献即表示同意以 MIT 授权。