from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.database import init_db
from app.models import Base
from app.services.scheduler import start_scheduler, stop_scheduler

app = FastAPI(title="Paper Local", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db(Base.metadata)
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()


app.include_router(router)

if settings.frontend_dist_dir.exists():
    # Serve built SPA for local desktop/web usage. API routes are matched before this mount.
    app.mount("/", StaticFiles(directory=str(settings.frontend_dist_dir), html=True), name="frontend")
