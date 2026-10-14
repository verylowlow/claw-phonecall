# AgentCallCenter (English)

**A Twilio-compatible local telephony bridge** — lets an OpenClaw `voice-call` setup keep
all of its AI capabilities (VAD, ASR, Agent, TTS, barge-in) while the audio path runs over
hardware you own, on-premise. No cloud telephony account, no per-minute billing.

> 中文文档见 [README.md](README.md)。

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Why

Twilio Media Streams is the easiest way to get real-time voice into an AI agent, but it is
a **metered cloud service** — every call ships audio, text and control frames to somebody
else's servers. That is a hard requirement for a lot of deployments: regulated data,
on-prem-only installs, or simply "this must work when the internet doesn't."

AgentCallCenter moves that layer local. It speaks Twilio's REST contract on the outside and
bridges the audio to whatever hardware you have on the desk — an LTE module, a USB voice
modem, or an Android phone. **The OpenClaw plugin config barely changes.**

```
OpenClaw voice-call <--REST/WebSocket--> AgentCallCenter Bridge <--hardware--> phone line
   (VAD/ASR/LLM/TTS)               (Twilio-compatible)   (SIM7600 / USB modem / Android)
```

---

## Features

| | |
|---|---|
| **Twilio REST compatible** | `POST /2010-04-01/Accounts/{sid}/Calls.json`, parses TwiML `<Stream>` |
| **Multiple hardware backends** | SIM7600 4G LTE (recommended) / SIM800C 2G / USB voice modem / Android / Mock |
| **Bidirectional audio** | 8 kHz μ-law ↔ 16-bit PCM over WebSocket, automatic resampling |
| **Barge-in** | Downstream `<clear>` flushes the playback queue |
| **Two-way recording** | Uplink and downlink saved separately as WAV, filed by number |
| **Web console** | Dashboard + call history (search / play / download) |
| **No hard native deps** | Pure-Python G.711 μ-law fallback when `audioop` is unavailable |

---

## Quick start

### 1. Install

```bash
git clone https://github.com/verylowlow/claw-phonecall.git
cd claw-phonecall
pip install -r requirements.txt
```

> `audioop` was removed from the standard library in Python 3.13. This repo ships a
> pure-Python G.711 μ-law implementation as a fallback, so it still runs even when
> `audioop-lts` cannot be installed.

### 2. Configure

```bash
cp .env.example .env
```

The one line you actually need to change first:

```env
BRIDGE_BACKEND=mock      # prove the loop with mock, then switch to real hardware
```

### 3. Run

```bash
python -m src.server
```

- Twilio REST API: `http://127.0.0.1:8080`
- Web console: `http://127.0.0.1:8080` (`/` dashboard, `/records` call history)

### 4. Point voice-call at the bridge

```json5
{
  plugins: {
    entries: {
      "voice-call": {
        enabled: true,
        config: {
          provider: "twilio",
          fromNumber: "+14155550123",
          twilio: {
            accountSid: "LOCAL_BRIDGE",
            authToken: "local_token",
            apiBaseUrl: "http://127.0.0.1:8080"   // ← point at the bridge
          },
          publicUrl: "http://127.0.0.1:8080/voice/webhook",
          streaming: { enabled: true, streamPath: "/voice/stream" }
        }
      }
    }
  }
}
```

Nothing else in the plugin changes.

---

## Hardware backends

### SIM7600 4G LTE (recommended)

```env
BRIDGE_BACKEND=sim7600
SIMCOM_AT_PORT=COM5       # AT command port
SIMCOM_AUDIO_PORT=COM6    # PCM audio port
SIMCOM_BAUD_RATE=115200
```

SIM7600G-H USB dongle + a 4G SIM. It enumerates several COM ports — find the AT port
and the audio port in Device Manager.

### SIM800C 2G GSM (development only)

```env
BRIDGE_BACKEND=sim800c
SIMCOM_AT_PORT=COM3
# SIMCOM_AUDIO_PORT=      # single shared port, leave empty
```

⚠️ 2G networks are being retired in most countries. Development use only.

### USB voice modem (landline)

```env
BRIDGE_BACKEND=usb_modem
MODEM_PORT=COM3
```

Wiring: phone line (RJ11) → USB voice modem → PC USB

### Android phone

```env
BRIDGE_BACKEND=android
ANDROID_DEVICE_ID=       # auto-detect if empty
```

Wiring: Android (USB + ADB) + external sound card + 3.5 mm cable

---

## Project layout

```
src/
├── server.py                # entry point (FastAPI + lifespan)
├── config.py                # env-driven configuration
├── bridge_manager.py        # call orchestration + media bridge loops
├── twilio_compat/           # Twilio compatibility layer
│   ├── rest_api.py          # POST /Calls.json
│   ├── twiml_parser.py      # parse TwiML <Stream>
│   └── webhook.py           # status callbacks
├── media_stream/
│   ├── ws_client.py         # WebSocket client (with reconnect)
│   ├── codec.py             # PCM ↔ μ-law ↔ base64
│   └── protocol.py          # Media Streams messages
├── backends/                # pluggable hardware backends
│   ├── base.py              # TelephonyBackend interface
│   ├── simcom_base.py       # SIMCom AT commands + URC + PCM threads
│   ├── sim7600.py / sim800c.py
│   ├── usb_modem.py / android.py / mock.py
├── recording/               # two-way recording
├── db/models.py             # SQLite persistence
└── web/                     # web console
```

---

## Gotchas (all fixed in this repo)

Not a weekend demo — these came out of real debugging. If you are writing your own
telephony backend, read this section first.

**1. `ATD` is asynchronous — `OK` does not mean connected**
`ATD<number>;` returns `OK` immediately, which only means "command accepted". The actual
connect result arrives a few hundred ms later as the URC `VOICE CALL: BEGIN`. An AT read
loop that breaks on `OK` will never see it → **calls never connect, and nothing logs an
error.** Hence the `_URC_DRAIN_S` window.

**2. URCs and command responses share one stream**
`BUSY` / `NO CARRIER` are both result codes *and* possible URCs. Conflating them makes a
failed call look like "some unrelated notification arrived", and the bridge marches on.
`_looks_like_urc()` keeps the two apart; result codes must reach the caller.

**3. pyserial objects are not thread-safe**
With a two-port module the URC thread reads the same AT port that `_at_cmd` reads.
Symptom is an intermittent "ATD got no response" that is nearly impossible to reproduce.
All serial I/O goes through `_serial_lock`.

**4. Do not start the URC thread on single-port modules (SIM800C)**
The AT port *is* the audio port; adding a third reader just makes things worse. Single-port
modules have `_at_cmd` extract the URC inline into `_pending_urc`, which
`_wait_for_connect` re-checks.

**5. `hangup()` must not always report success**
If `ATH` returns `ERROR` and the bridge still assumes success, the line stays occupied
and the *next* call fails to connect — a confusing symptom to debug. Now `OK` /
`NO CARRIER` count as released, anything else is a failure.

**6. μ-law bit width**
The classic mistake when hand-rolling this: the input is arithmetically shifted right by 2
into 14 bits, so the segment table is 0x3F…0x1FFF, **not** 0xFF…0x7FFF. Verified by
37.1 dB round-trip SNR and the 32124 decode full-scale.

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE).

The audio path, Twilio compatibility layer and hardware abstraction are independently
reusable. Commercial AI capabilities (ASR / LLM / TTS) are **not** part of this repo —
this project is transport only.