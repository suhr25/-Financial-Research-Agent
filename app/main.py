from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import BASE_DIR, get_settings
from app.storage.database import init_db

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("financial_research_agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(
        "Startup complete. demo_mode=%s llm_provider=%s llm_available=%s",
        settings.effective_demo_mode,
        settings.llm_provider,
        settings.llm_available,
    )
    yield


app = FastAPI(title="Financial Research Agent", version="0.1.0", lifespan=lifespan)

app.include_router(router, prefix="/api")

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
