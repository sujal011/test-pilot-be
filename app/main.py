from __future__ import annotations

import logging

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

    # INSERT_YOUR_CODE
# @app.get("/docs", include_in_schema=False)
# async def custom_docs_redirect():
#     from fastapi.responses import RedirectResponse
#     return RedirectResponse(url="/docs/")