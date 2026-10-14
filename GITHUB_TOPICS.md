# GitHub Topics 设置清单

仓库：https://github.com/verylowlow/claw-phonecall

Topics 是 GitHub **唯一免费**的站内分发标签。设置完成后，仓库会出现在
`github.com/topics/twilio` 等聚合页里被搜索到——这是本项目长尾曝光的主要入口。

## 建议的 20 个 topics

在仓库主页右侧栏「About → Topics」逐个添加：

```
twilio                    # 核心兼容目标，流量最大
telephony                 # 领域主词
voip
sip
asterisk                  #  telephony 三大流量池之一
freeswitch
webrtc
twiml
media-streams             # 精确匹配本项目实现
pstn
voice-gateway
bridge
openclaw
llm
asr
tts
vad
audio
python
fastapi
```

> GitHub 最多 20 个，**必须刚好填满 20**——填不满会浪费免费曝光位。

## 设置步骤

1. 打开 `https://github.com/verylowlow/claw-phonecall`
2. 右侧栏点齿轮图标（⚙）→ 找到 Topics
3. 输入框逐个填入上面 20 个词，每个词输完按回车
4. 页面刷新后确认 20 个全部显示

## 一并要改的

| 项 | 现值 | 应改为 |
|---|---|---|
| Description | `help the openclaw agent making a phonecall with out voIP service, with your own sitting-by phone` | `Twilio-compatible local telephony bridge. Run OpenClaw voice-call over your own SIM7600 / USB modem / Android. No cloud, no per-minute billing.` |
| Website | 空 | 可留空（不留微信号/邮箱，平台规则） |
| Discussions | 已开启 ✅ | 保持 |
| Issues | 已开启 ✅ | 保持 |

## 为什么 description 要改

现值语法有误（`with out` 应为 `without`，`voIP` 大小写混乱），且完全没有提到
"Twilio 兼容""本地部署"这两个真正的差异化卖点——搜索这两个词的开发者看不到本仓库。

## 合规红线

⚠️ **GitHub 上严禁留微信号或邮箱**。只留体验线号码或官网。
每批发布前自检：

```bash
git grep -niE "shitren|微信|weixin|qq|@.*\.com"
```