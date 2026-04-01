"""Tests for Twilio Media Stream protocol message building/parsing."""

import json
import pytest

from src.media_stream.protocol import (
    build_start_message,
    build_media_message,
    build_stop_message,
    build_clear_message,
    build_mark_message,
    parse_message,
)


def test_build_start_message():
    raw = build_start_message("MS123", "CA456", "AC789", token="tok_abc")
    msg = json.loads(raw)
    assert msg["event"] == "start"
    assert msg["streamSid"] == "MS123"
    assert msg["start"]["callSid"] == "CA456"
    assert msg["start"]["accountSid"] == "AC789"
    assert msg["start"]["customParameters"]["token"] == "tok_abc"
    assert msg["start"]["mediaFormat"]["encoding"] == "audio/x-mulaw"
    assert msg["start"]["mediaFormat"]["sampleRate"] == 8000


def test_build_start_message_no_token():
    raw = build_start_message("MS123", "CA456", "AC789")
    msg = json.loads(raw)
    assert msg["start"]["customParameters"] == {}


def test_build_media_message():
    raw = build_media_message("MS123", "AQID", 2, 1, 20)
    msg = json.loads(raw)
    assert msg["event"] == "media"
    assert msg["streamSid"] == "MS123"
    assert msg["media"]["payload"] == "AQID"
    assert msg["media"]["track"] == "inbound"


def test_build_stop_message():
    raw = build_stop_message("MS123")
    msg = json.loads(raw)
    assert msg["event"] == "stop"
    assert msg["streamSid"] == "MS123"


def test_build_clear_message():
    raw = build_clear_message("MS123")
    msg = json.loads(raw)
    assert msg["event"] == "clear"


def test_build_mark_message():
    raw = build_mark_message("MS123", "utterance_end")
    msg = json.loads(raw)
    assert msg["event"] == "mark"
    assert msg["mark"]["name"] == "utterance_end"


def test_parse_message():
    msg = parse_message('{"event":"media","media":{"payload":"abc"}}')
    assert msg["event"] == "media"


def test_parse_message_non_dict():
    msg = parse_message('"just a string"')
    assert msg["event"] == "unknown"
