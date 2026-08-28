import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
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

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# 统一错误响应（契约 §1）：{code, message, detail?}
# ---------------------------------------------------------------------------

_STATUS_CODE_TO_CODE = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid_request",
}


def _code_for_status(status_code: int) -> str:
    return _STATUS_CODE_TO_CODE.get(status_code, "invalid_request")


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """统一 HTTP 异常响应；兼容已结构化的 detail 与历史遗留的裸字符串。"""
    detail = exc.detail
    if isinstance(detail, dict):
        payload = {
            "code": detail.get("code", _code_for_status(exc.status_code)),
            "message": str(detail.get("message", "请求失败")),
        }
        if detail.get("detail") is not None:
            payload["detail"] = detail["detail"]
    else:
        payload = {
            "code": _code_for_status(exc.status_code),
            "message": str(detail) if detail else "请求失败",
        }
    return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """请求体/参数校验失败统一为 ``invalid_request``。"""
    errors = [
        {"loc": ".".join(str(part) for part in err.get("loc", ())), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "code": "invalid_request",
            "message": "请求参数校验失败",
            "detail": {"errors": errors},
        },
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常：记 traceback 用于排查，响应不泄露内部细节。"""
    logger.exception("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "message": "服务器内部错误，请稍后重试"},
    )


# ---------------------------------------------------------------------------
# 前端静态资源：只服务 web/dist（React SPA）
# ---------------------------------------------------------------------------


def _index_exists() -> bool:
    return (_DIST_DIR / "index.html").is_file()


@app.get("/", response_class=FileResponse)
def index() -> Response:
    if not _index_exists():
        return JSONResponse(
            status_code=404,
            content={
                "code": "not_found",
                "message": "前端未构建：请先在 web/ 目录执行 pnpm build",
            },
        )
    return FileResponse(_DIST_DIR / "index.html")


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/{full_path:path}")
def spa_assets(full_path: str) -> Response:
    """服务已构建的 React 资源；SPA 路由兜底回 index.html。

    Must be registered last so explicit API routes (e.g. ``/v1/health``) win.
    """
    if not _index_exists():
        return JSONResponse(
            status_code=404,
            content={
                "code": "not_found",
                "message": "前端未构建：请先在 web/ 目录执行 pnpm build",
            },
        )
    asset = _DIST_DIR / full_path
    if asset.is_file() and _DIST_DIR in asset.resolve().parents:
        return FileResponse(asset)
    return FileResponse(_DIST_DIR / "index.html")


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
