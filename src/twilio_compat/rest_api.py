import inspect
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException

from src.bridge_manager import initiate_call

logger = logging.getLogger(__name__)

router = APIRouter()

_active_calls: dict[str, dict[str, Any]] = {}


def get_active_call(call_sid: str) -> dict | None:
    return _active_calls.get(call_sid)


def update_call_status(call_sid: str, status: str) -> None:
    if call_sid in _active_calls:
        _active_calls[call_sid]["status"] = status


def remove_call(call_sid: str) -> None:
    _active_calls.pop(call_sid, None)


def _new_call_sid() -> str:
    return "CA" + uuid.uuid4().hex


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _run_initiate_call(
    call_sid: str,
    account_sid: str,
    to: str,
    from_number: str,
    url: str,
    status_callback: str | None,
    status_callback_event: str | None,
) -> None:
    try:
        result = initiate_call(
            call_sid=call_sid,
            account_sid=account_sid,
            to=to,
            from_number=from_number,
            url=url,
            status_callback=status_callback,
            status_callback_event=status_callback_event,
        )
        if inspect.iscoroutine(result):
            await result
    except Exception:
        logger.exception("initiate_call failed for %s", call_sid)


@router.post("/2010-04-01/Accounts/{account_sid}/Calls.json")
async def create_call(
    account_sid: str,
    background_tasks: BackgroundTasks,
    To: str = Form(...),
    From: str = Form(...),
    Url: str = Form(...),
    StatusCallback: str | None = Form(default=None),
    StatusCallbackEvent: str | None = Form(default=None),
) -> dict[str, Any]:
    call_sid = _new_call_sid()
    date_created = _iso_utc()
    _active_calls[call_sid] = {
        "sid": call_sid,
        "status": "queued",
        "to": To,
        "from": From,
        "date_created": date_created,
        "account_sid": account_sid,
        "url": Url,
        "status_callback": StatusCallback,
        "status_callback_event": StatusCallbackEvent,
    }
    background_tasks.add_task(
        _run_initiate_call,
        call_sid,
        account_sid,
        To,
        From,
        Url,
        StatusCallback,
        StatusCallbackEvent,
    )
    return {
        "sid": call_sid,
        "status": "queued",
        "to": To,
        "from": From,
        "date_created": date_created,
    }


def _call_json(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "sid": record["sid"],
        "status": record["status"],
        "to": record["to"],
        "from": record["from"],
        "date_created": record["date_created"],
    }


@router.post("/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json")
async def update_call(
    account_sid: str,
    call_sid: str,
    Status: str = Form(...),
) -> dict[str, Any]:
    record = get_active_call(call_sid)
    if record is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if record.get("account_sid") != account_sid:
        raise HTTPException(status_code=404, detail="Call not found")
    if Status == "completed":
        update_call_status(call_sid, "completed")
        record = get_active_call(call_sid) or record
    return _call_json(record)
