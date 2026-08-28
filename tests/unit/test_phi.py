from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from care_lifeline.api.middleware.phi import PHIMiddleware
from care_lifeline.safety.phi import mask


def test_mask_id_card_replaced() -> None:
    out = mask("身份证 11010119900307891X 已登记")
    assert "[PHI]" in out
    assert "11010119900307891X" not in out


def test_mask_phone_replaced() -> None:
    out = mask("联系电话 13800138000")
    assert "[PHI]" in out
    assert "13800138000" not in out


def test_mask_name_replaced() -> None:
    out = mask("姓名：张三，来看诊")
    assert "[PHI]" in out
    assert "张三" not in out


def test_mask_medical_record_replaced() -> None:
    out = mask("病历号 M20260828 已建档")
    assert "[PHI]" in out
    assert "M20260828" not in out


def test_mask_plain_text_unchanged() -> None:
    assert mask("建议患者多休息") == "建议患者多休息"


def test_mask_idempotent() -> None:
    once = mask("姓名：张三 身份证 11010119900307891X")
    twice = mask(once)
    assert twice == once


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(PHIMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"body": body.decode("utf-8")}

    return app


def test_middleware_masks_request_body() -> None:
    client = TestClient(_make_app())
    payload = '{"text":"我叫张三 身份证 11010119900307891X 电话 13800138000"}'
    headers = {"content-type": "application/json"}
    resp = client.post("/echo", content=payload.encode("utf-8"), headers=headers)
    body = resp.json()["body"]
    assert "[PHI]" in body
    assert "张三" not in body
    assert "11010119900307891X" not in body
    assert "13800138000" not in body


def test_middleware_passes_plain_body_unchanged() -> None:
    client = TestClient(_make_app())
    payload = '{"text":"建议患者多休息"}'
    headers = {"content-type": "application/json"}
    resp = client.post("/echo", content=payload.encode("utf-8"), headers=headers)
    assert resp.json()["body"] == payload
