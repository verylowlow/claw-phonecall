"""Tests for TwiML parser."""

from src.twilio_compat.twiml_parser import parse_twiml


def test_parse_stream_url():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="wss://example.com/voice/stream">
                <Parameter name="token" value="abc123"/>
            </Stream>
        </Connect>
    </Response>"""
    result = parse_twiml(xml)
    assert result["stream_url"] == "wss://example.com/voice/stream"
    assert result["parameters"]["token"] == "abc123"


def test_parse_no_stream():
    xml = "<Response><Say>Hello</Say></Response>"
    result = parse_twiml(xml)
    assert result["stream_url"] is None
    assert result["parameters"] == {}


def test_parse_stream_no_params():
    xml = '<Response><Connect><Stream url="wss://x.com/s"/></Connect></Response>'
    result = parse_twiml(xml)
    assert result["stream_url"] == "wss://x.com/s"
    assert result["parameters"] == {}
