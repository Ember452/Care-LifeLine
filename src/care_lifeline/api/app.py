from fastapi import FastAPI

from care_lifeline.api.routers import chat

app = FastAPI(title="Care-LifeLine", version="0.2.0")

app.include_router(chat.router, prefix="/v1")


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok"}
