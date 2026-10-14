"""Web management API routes for AgentCallCenter dashboard."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from src.db import models
from src.recording.storage import get_recording_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["web"])


@router.get("/dashboard")
def dashboard():
    """Dashboard statistics for the console panel."""
    stats = models.get_dashboard_stats()
    devices = models.list_devices()
    sessions = {}
    try:
        from src.bridge_manager import get_all_sessions
        for sid, s in get_all_sessions().items():
            sessions[sid] = {
                "call_sid": s.call_sid,
                "to": s.to,
                "status": s.status,
                "duration": int(__import__("time").time() - s.start_time),
            }
    except Exception:
        pass

    return {
        **stats,
        "devices": devices,
        "active_sessions": sessions,
    }


@router.get("/devices")
def list_devices():
    return models.list_devices()


@router.get("/calls")
def list_calls(
    phone: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    backend: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    rows = models.list_calls(
        phone_number=phone,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        backend_type=backend,
        status=status,
        limit=page_size,
        offset=offset,
    )
    total = models.count_calls(
        phone_number=phone,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 1,
    }


@router.get("/calls/{call_id}")
def get_call(call_id: str):
    row = models.get_call(call_id)
    if not row:
        raise HTTPException(404, "Call not found")
    return row


@router.get("/calls/{call_id}/recording")
def get_recording(call_id: str, download: bool = Query(False)):
    row = models.get_call(call_id)
    if not row or not row.get("recording_path"):
        raise HTTPException(404, "Recording not found")

    path = get_recording_path(row["recording_path"])
    if not path:
        raise HTTPException(404, "Recording file missing")

    media_type = "audio/wav"
    if download:
        return FileResponse(
            str(path), media_type=media_type,
            filename=path.name,
            headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
        )
    return FileResponse(str(path), media_type=media_type)
