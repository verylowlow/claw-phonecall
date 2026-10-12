# 建议为仓库添加的 Topics（GitHub 最多 20 个）

> 添加位置：仓库主页 → 右侧 About → 旁边的齿轮 ⚙ → Topics
> 建议一次全选粘贴。Topics 是 GitHub 长尾搜索曝光的主要入口之一，
> **对本仓库（公开、可被搜索引擎收录）比 README 优化更直接地影响曝光。**

## 建议填写（20 个）

```
openclaw
openclaw-skill
android
adb
telephony
phone-call
voice-ai
asr
tts
tts-edge
vad
real-time
audio-capture
alsa
multi-agent
automation
llm
agent-skill
telecom
edge-tts
```

## 选择理由

| topic | 承接什么搜索意图 |
|---|---|
| `openclaw` / `openclaw-skill` / `agent-skill` | OpenClaw 生态内的技能目录检索 |
| `android` / `adb` | 「用安卓手机做 X」类搜索 |
| `telephony` / `phone-call` / `telecom` | 电话外呼/来电方向的核心词 |
| `voice-ai` / `llm` / `asr` | 「AI 语音对话」大词 |
| `tts` / `tts-edge` / `edge-tts` | EdgeTTS 是本项目免费方案，蹭精确词 |
| `vad` / `alsa` / `audio-capture` / `real-time` | 技术实现细节，长尾精准 |
| `multi-agent` / `automation` | Agent 编排方向 |

## 同时建议修改的仓库设置

| 位置 | 当前（2026-10-12 实测） | 建议改为 |
|---|---|---|
| About → Description | 英文且与内容不符 | `用一台已 Root 的安卓手机，让 AI Agent 打电话：ADB 控制 + ALSA/FIFO 低延迟音频 + 流式 ASR + EdgeTTS` |
| About → Website | 空 | 留空（**不要在 GitHub 留微信号 / 邮箱，违反平台规则**） |
| Discussions | 未开启 | **开启**，6 个分类：Q&A / Show and tell / Ideas / General / Help / 公告 |
| Issues | 无模板 | 已随本批加入 3 个模板（Bug / Device / Feature） |
| License | **无 LICENSE 文件** | 待老板拍板（建议 BUSL 1.1：可见源码、可自部署、禁直接商用） |