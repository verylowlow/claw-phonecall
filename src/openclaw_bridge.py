"""
通过 OpenClaw Gateway 的 OpenResponses HTTP API 获取 Agent 最终回复文本（非流式）。
与 @openclaw/voice-call 中 generateVoiceResponse → runEmbeddedPiAgent 语义一致：一次调用得到完整回复。

文档: https://docs.openclaw.ai/gateway/openresponses-http-api
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def _extract_text_deep(obj: Any) -> Optional[str]:
    """从 OpenResponses/兼容 JSON 中尽力提取 assistant 文本。"""
    if obj is None:
        return None
    if isinstance(obj, str):
        s = obj.strip()
        return s if s else None
    if isinstance(obj, dict):
        if obj.get("type") in ("output_text", "text") and isinstance(obj.get("text"), str):
            t = obj["text"].strip()
            if t:
                return t
        if isinstance(obj.get("content"), list):
            parts = []
            for c in obj["content"]:
                t = _extract_text_deep(c)
                if t:
                    parts.append(t)
            if parts:
                return "\n".join(parts)
        for v in obj.values():
            t = _extract_text_deep(v)
            if t:
                return t
    if isinstance(obj, list):
        parts = []
        for it in obj:
            t = _extract_text_deep(it)
            if t:
                parts.append(t)
        if parts:
            return "\n".join(parts)
    return None


def request_agent_text(
    user_message: str,
    *,
    transcript_lines: Optional[List[str]] = None,
    instructions: Optional[str] = None,
    session_user: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    调用 Gateway POST /v1/responses（非流式），返回模型最终文本。

    Args:
        timeout: HTTP 超时秒数。None 时从 CALL_CONFIG["gateway_timeout_s"] 读取（默认 10）。

    环境变量:
      OPENCLAW_GATEWAY_URL  默认 http://127.0.0.1:18789
      OPENCLAW_GATEWAY_TOKEN Bearer token（与 Gateway 配置一致）
      OPENCLAW_AGENT_ID     可选，如 main
      OPENCLAW_SESSION_USER 可选，稳定会话路由（建议用手机号）
    """
    base = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/")
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    agent_id = os.environ.get("OPENCLAW_AGENT_ID", "main").strip()
    session_user = (session_user or os.environ.get("OPENCLAW_SESSION_USER", "")).strip()

    url = f"{base}/v1/responses"
    sys_extra = instructions or (
        "你是电话客服助手。回答要简短、口语化，一两句话即可。"
        "不要输出思考过程或 Markdown。"
    )
    history = transcript_lines or []
    if history:
        sys_extra = sys_extra + "\n\n通话记录：\n" + "\n".join(history)

    items: list[dict[str, Any]] = []
    if sys_extra:
        items.append({"type": "message", "role": "developer", "content": sys_extra})
    items.append({"type": "message", "role": "user", "content": user_message})

    body: dict[str, Any] = {
        "model": "openclaw",
        "stream": False,
        "input": items,
    }
    if session_user:
        body["user"] = session_user

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if agent_id:
        headers["x-openclaw-agent-id"] = agent_id

    if timeout is None:
        try:
            from .config import CALL_CONFIG
            timeout = int(CALL_CONFIG.get("gateway_timeout_s", 10))
        except Exception:
            timeout = 10

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        logger.error("OpenClaw Gateway HTTP %s: %s", e.code, err_body[:2000])
        return None
    except Exception as e:
        logger.error("OpenClaw Gateway request failed: %s", e)
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("OpenClaw Gateway returned non-JSON")
        return None

    text = _extract_text_deep(payload)
    if text:
        return text.strip()
    logger.warning("OpenClaw response had no extractable text: keys=%s", list(payload.keys()) if isinstance(payload, dict) else type(payload))
    return None


def notify_call_ended(
    phone_number: str,
    duration_s: int,
    transcript_lines: Optional[List[str]] = None,
) -> None:
    """Best-effort 通知 Gateway 通话结束（不阻塞、不抛异常）。"""
    try:
        request_agent_text(
            f"[系统通知] 与 {phone_number} 的通话已结束，时长 {duration_s} 秒。",
            transcript_lines=transcript_lines,
            session_user=phone_number,
            timeout=5,
        )
    except Exception as e:
        logger.debug("notify_call_ended failed (best-effort): %s", e)


def mock_reply(user_message: str) -> str:
    """未配置 Gateway 时的占位回复（可通过环境变量覆盖）。"""
    custom = os.environ.get("PHONE_SKILL_MOCK_REPLY", "").strip()
    if custom:
        return custom
    return "好的，我记下了。请问还有什么需要帮您的？"
