import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from care_lifeline.api.middleware.phi import PHIMiddleware
from care_lifeline.api.routers import auth, chat, hitl
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Care-LifeLine", version="0.2.0")
app.add_middleware(PHIMiddleware)

app.include_router(chat.router, prefix="/v1")
app.include_router(auth.router)
app.include_router(hitl.router)


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.on_event("startup")
async def _startup() -> None:
    if get_settings().database_url.startswith("sqlite"):
        with contextlib.suppress(Exception):  # DB may be unavailable in some envs
            init_db()
            session_store.seed_demo_user()


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok"}
