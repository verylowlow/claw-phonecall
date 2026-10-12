# Claw Phone Call

**Let an AI Agent place phone calls using the Android phone already on your desk.**
No VoIP service to buy, no number to apply for, no SIP trunk to provision — one rooted Android phone and one USB cable is a phone your Agent can drive.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![OpenClaw](https://img.shields.io/badge/skill-OpenClaw-purple.svg)](SKILL.md)
[![License](https://img.shields.io/badge/license-source--available-informational.svg)](#license)

> 中文文档见 [README.md](README.md)。This is the English version.

---

## Why "just use the phone you already own"

Building AI voice calling usually means picking one of three options, each with its own pain point:

| Option | The pain |
|---|---|
| Cloud AI outreach SaaS | Numbers get flagged fast and connect rates drop; call data lives on someone else's servers; per-minute billing forever |
| SIP trunk / VoIP number | Requires a business registration; virtual numbers get classified as marketing lines; painful to configure |
| Buy a voice gateway | Hardware is only the start — now you own the SIP stack and the drivers |

**This project takes a different route: use the phone you already have.** A phone *is* a standard telephone. Insert a SIM and it dials — with a real mobile number and real network quality — using no provider account and no approval process.

Combined with OpenClaw's Agent capabilities, your Agent can call a phone the same way it calls any other tool.

---

## Capabilities

| Capability | Details |
|---|---|
| 📞 **Call control** | Dial, answer, hang up, DTMF keypress, call-state detection |
| 🎙️ **Low-latency audio capture** | ALSA + FIFO pipe design, ~**50 ms** audio-side latency |
| 🗣️ **Streaming speech recognition** | Volcengine SeedASR streaming transcription (bring your own `app_id` / `access_token`) |
| 🔊 **Speech synthesis** | **EdgeTTS** (Microsoft Edge engine — **free, no API key**) |
| 🔊 **VAD** | Voice activity detection to separate speech from silence, with silence-filler phrases |
| 📱 **Multi-device concurrency** | Multiple phones in simultaneous calls, orchestrated as one pool |
| 🛠️ **Full device control** | Tap, swipe, Home / power keys, text input, screenshot, start/stop apps |

### Conversation loop

```
Agent issues command → dial → wait for answer → play greeting
   ↓
┌─ loop ───────────────────────────────┐
│ capture audio → VAD → ASR transcript │
│    → LLM → TTS synthesis → play     │
└─────────────────────────────────────┘
   ↓
end keyword hit / max turns reached → hang up
```

---

## Requirements

- **A rooted Android phone** (root is required to reach the ALSA audio devices)
- USB data cable + USB debugging enabled
- Python 3.9+ on the host machine

Recommended devices: models with active rooting communities — Xiaomi, OnePlus, realme.

> **Why root?** The audio path runs on the phone's own ALSA devices through a FIFO pipe.
> That is what makes ~50 ms latency achievable. Unrooted devices cannot open this path.

---

## Quick start

### 1. Install dependencies

```bash
git clone https://github.com/verylowlow/claw-phonecall.git
cd claw-phonecall
pip install -r requirements.txt
```

### 2. Configure

Edit `configs/settings.yaml`:

```yaml
adb:
  mode: usb                # usb or wifi
  devices:
    - id: "phone1"
      serial: "ABCD123456789"    # serial from `adb devices`
      name: "Test phone 1"
      phone_number: "13511223344"

volcengine:
  region: cn-beijing
  asr:
    app_id: "YOUR_APP_ID"
    access_token: "YOUR_ACCESS_TOKEN"
    resource_id: "volc.seedasr.auc"   # SeedASR model 2.0
```

> 🔒 **Credentials**: TTS uses EdgeTTS and needs **no key at all**; only ASR requires Volcengine credentials.
> Keep real tokens out of the repository — use placeholders in the committed config
> and keep your real values in a local, untracked file or environment variables.

### 3. Verify the device

```bash
adb devices          # status should be `device`, not `unauthorized`
python scripts/phone_call.py list
```

### 4. Use it

**Python**

```python
from scripts.phone_call import PhoneCall

phone = PhoneCall("ABCD123456789")

# one-shot: dial → wait → converse → hang up
phone.run_full_call("13800138000", greeting="Hi, this is an AI assistant. How can I help?")

# or drive each step yourself
phone.dial("13800138000")
if phone.wait_for_answer(timeout=30):
    phone.start_conversation()
    phone.hangup()
```

**CLI**

```bash
python scripts/phone_call.py list              # list connected devices
python scripts/phone_call.py -s ABCD123 info   # device info
python scripts/phone_call.py -s ABCD123 dial 13800138000
```

**Multiple phones**

```python
from scripts.phone_call import PhoneCallManager

manager = PhoneCallManager()
manager.add_device("phone1", "ABCD123456", "13511111111")
manager.add_device("phone2", "EFGH789012", "13522222222")

connected = manager.dial_and_connect([
    ("phone1", "13800138000"),
    ("phone2", "13900139000"),
])
```

**As an OpenClaw skill**

[`SKILL.md`](SKILL.md) is a standard OpenClaw skill definition declaring trigger
conditions and allowed tools — OpenClaw can load it directly.

---

## Project layout

```
claw-phonecall/
├── SKILL.md                # OpenClaw skill definition
├── README.md               # Chinese documentation
├── requirements.txt
├── configs/
│   └── settings.yaml       # device + ASR/TTS configuration
└── scripts/
    ├── adb_control.py      # ADB device control (dial / keys / tap / screenshot)
    ├── audio_capture.py    # ALSA + FIFO audio capture and playback
    ├── vad.py              # voice activity detection + silence filling
    ├── asr_client.py       # Volcengine SeedASR client
    ├── tts_player.py       # EdgeTTS player
    ├── dialog_manager.py   # conversation state machine + multi-device orchestration
    └── phone_call.py       # main entry point / CLI
```

---

## FAQ

**Q: What's the latency?**
About 50 ms on the audio side (ALSA + FIFO). End-to-end also depends on ASR/TTS network round-trips.

**Q: Is root really required?**
Yes. Accessing ALSA audio devices requires root — it is the premise of the low-latency design.

**Q: Which phones are supported?**
Any rooted Android device. Prefer models with active rooting communities and configurable screen-on behaviour.

**Q: How many simultaneous calls?**
One per phone you connect. Each phone registers as an independent device in the `devices` list.

**Q: Can this be used for spam calling?**
No. Only dial numbers where you have a legitimate business relationship (order notifications, service follow-ups, etc.).
Bulk dialling of unsolicited numbers violates telecom regulations; this project neither provides nor supports that use case.

---

## Safety notes

- This project **drives your real phone**: dialing, tapping, starting and stopping apps. **Confirm your device configuration before running.**
- Calls consume carrier minutes.
- Use a headset to avoid echo feedback causing the AI to talk to itself.
- **Never commit real credentials (`app_id` / `access_token` / device serials) to a public repository.**

---

## ⭐ Star this project

If this saved you a VoIP account and a pile of configuration, drop a **Star** ⭐ so more people who need it can find it.

<p align="center">
  <b>Need a full appliance that answers landlines / 400 numbers?</b><br>
  An all-in-one AI phone receptionist (on-premise · private deployment · works offline)<br>
  is running in production — call the demo line <b>165-1124-4888</b> to hear the AI answer.
</p>

---

## License

Source code may be freely read, modified and self-deployed. **Commercial redistribution and resale require authorization.**
A LICENSE file has not yet been added — do not assume any license terms until one is published.