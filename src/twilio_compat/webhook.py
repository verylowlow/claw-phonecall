import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _default_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def send_status_callback(
    callback_url: str,
    call_sid: str,
    status: str,
    from_number: str,
    to_number: str,
    **extra: Any,
) -> dict | None:
    form: dict[str, str] = {k: str(v) for k, v in extra.items()}
    form.setdefault("Direction", "outbound-api")
    form.setdefault("Timestamp", _default_timestamp())
    form.setdefault("AccountSid", "")
    form.update(
        {
            "CallSid": call_sid,
            "CallStatus": status,
            "From": from_number,
            "To": to_number,
        }
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(callback_url, data=form)
            if r.is_error:
                logger.warning(
                    "status callback HTTP %s from %s",
                    r.status_code,
                    callback_url,
                )
            ct = (r.headers.get("content-type") or "").lower()
            if "application/json" in ct:
                try:
                    body = r.json()
                    return body if isinstance(body, dict) else {"body": body}
                except Exception:
                    return {"body": r.text}
            return {"body": r.text}
    except Exception:
        logger.exception("status callback failed: %s", callback_url)
        return None


async def fetch_twiml(
    url: str,
    call_sid: str,
    from_number: str,
    to_number: str,
) -> str | None:
    data = {
        "CallSid": call_sid,
        "From": from_number,
        "To": to_number,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, data=data)
            if r.is_error:
                logger.warning("fetch twiml HTTP %s from %s", r.status_code, url)
                return None
            return r.text
    except Exception:
        logger.exception("fetch twiml failed: %s", url)
        return None
