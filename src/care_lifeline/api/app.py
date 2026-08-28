import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.responses import Response

from care_lifeline.api.middleware.phi import PHIMiddleware
from care_lifeline.api.routers import (
    admin,
    auth,
    chat,
    hitl,
    medication,
    ocr,
    patients,
    reports,
    workbench,
)
from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db
from care_lifeline.graph.checkpointer import ensure_checkpointer_setup
from care_lifeline.proactive import scheduler as proactive_scheduler

_STATIC_DIR = Path(__file__).parent / "static"
_DIST_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"

app = FastAPI(title="Care-LifeLine", version="0.2.0")
app.add_middleware(PHIMiddleware)

app.include_router(chat.router, prefix="/v1")
app.include_router(auth.router)
app.include_router(hitl.router)
app.include_router(reports.router)
app.include_router(patients.router)
app.include_router(workbench.router)
app.include_router(admin.router)
app.include_router(medication.router)
app.include_router(ocr.router)


def _index_path() -> Path:
    candidate = _DIST_DIR / "index.html"
    return candidate if candidate.exists() else _STATIC_DIR / "index.html"


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(_index_path())


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
async def _startup() -> None:
    with contextlib.suppress(Exception):  # DB may be unavailable in some envs
        init_db()
        session_store.seed_demo_user()
    await ensure_checkpointer_setup()
    proactive_scheduler.start_scheduler()


@app.on_event("shutdown")
async def _shutdown() -> None:
    proactive_scheduler.stop_scheduler()


@app.get("/{full_path:path}")
def spa_assets(full_path: str) -> Response:
    """Serve built React assets; SPA fallback to index.html for client routing.

    Must be registered last so explicit API routes (e.g. ``/v1/health``) win.
    """
    asset = _DIST_DIR / full_path
    if asset.is_file() and _DIST_DIR in asset.resolve().parents:
        return FileResponse(asset)
    return FileResponse(_index_path())
