from __future__ import annotations

import asyncio
import logging
import sys

# ── Windows: asyncio subprocess support ───────────────────────────────────────
# SelectorEventLoop (Windows default) does NOT support subprocess creation.
# Switch to ProactorEventLoop so asyncio.create_subprocess_exec works correctly.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import projects, stories, test_cases, test_runs
from app.routers import streaming

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(
    title="Agent Test Platform",
    description="AI-powered browser automation testing — local MVP",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(projects.router)
app.include_router(stories.router)
app.include_router(test_cases.router)
app.include_router(test_runs.router)
app.include_router(streaming.router)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}