"""AgentCallCenter — main HTTP + WebSocket server."""

import logging
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.config import BRIDGE_CONFIG, configure_logging

logger = logging.getLogger(__name__)

_static_dir = Path(__file__).resolve().parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("============================================================")
    logger.info(" AgentCallCenter — Twilio-compatible local telephony bridge ")
    logger.info("============================================================")

    from src import bridge_manager
    await bridge_manager.init_db()
    await bridge_manager.start_device_monitoring()

    yield

    await bridge_manager.shutdown()


app = FastAPI(title="AgentCallCenter Bridge", lifespan=lifespan)

from src.twilio_compat.rest_api import router as twilio_router
from src.web.api import router as web_router

app.include_router(twilio_router)
app.include_router(web_router)

if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index_page():
    html = _static_dir / "index.html"
    return html.read_text(encoding="utf-8") if html.exists() else "<h1>AgentCallCenter</h1>"


@app.get("/records", response_class=HTMLResponse)
async def records_page():
    html = _static_dir / "records.html"
    return html.read_text(encoding="utf-8") if html.exists() else "<h1>Records</h1>"


def main() -> None:
    uvicorn.run(
        "src.server:app",
        host=BRIDGE_CONFIG["host"],
        port=BRIDGE_CONFIG["port"],
    )


if __name__ == "__main__":
    main()
