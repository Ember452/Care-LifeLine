from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from care_lifeline.api.middleware.phi import PHIMiddleware
from care_lifeline.safety.phi import detect_kinds, detect_phi_leak, mask


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
    assert "来看诊" in out  # 姓名值只吃 2-4 个字，不再吞掉后续句子


def test_mask_medical_record_replaced() -> None:
    out = mask("病历号 M20260828 已建档")
    assert "[PHI]" in out
    assert "M20260828" not in out
    assert "病历号" in out  # 标签保留，只替换值


def test_mask_plain_text_unchanged() -> None:
    assert mask("建议患者多休息") == "建议患者多休息"


def test_mask_idempotent() -> None:
    once = mask("姓名：张三 身份证 11010119900307891X")
    twice = mask(once)
    assert twice == once


# --------------------------------------------------------------------------
# 检测纵深：新增类型
# --------------------------------------------------------------------------


def test_mask_email_replaced() -> None:
    out = mask("报告发到 patient.zhang@example.com 即可")
    assert "[PHI]" in out
    assert "patient.zhang@example.com" not in out


def test_mask_birth_date_replaced() -> None:
    out = mask("出生日期：1990-03-07，按计划复诊")
    assert "出生日期[PHI]" in out
    assert "1990-03-07" not in out


def test_mask_labeled_age_replaced() -> None:
    out = mask("年龄：45 岁，无既往史")
    assert "年龄[PHI]" in out
    assert "45" not in out.split("年龄")[1].split("岁")[0]


def test_mask_unlabeled_age_kept_for_clinical_value() -> None:
    # 只有显式「年龄」字段才算标识符；自由文本的「45岁」保留临床价值。
    assert mask("患者 45 岁") == "患者 45 岁"


def test_mask_address_replaced() -> None:
    out = mask("住址：北京市朝阳区望京街道45号楼， nearby")
    assert "住址[PHI]" in out
    assert "北京市朝阳区望京街道45号楼" not in out


def test_mask_social_account_replaced() -> None:
    out = mask("微信号 wxid_abc12345 有问题随时联系")
    assert "微信号[PHI]" in out
    assert "wxid_abc12345" not in out


def test_mask_name_title_heuristic() -> None:
    out = mask("张医生建议复查，王女士同意了，老李也一起来")
    assert "张" not in out.replace("[PHI]", "")
    assert "医生" in out  # 称谓保留，语义不丢
    assert "[PHI]女士" in out
    assert "老李" not in out


def test_mask_name_title_no_false_positive() -> None:
    # 「小心」「老师傅」这类非姓名组合不应误伤
    assert "小心" in mask("走路要小心")
    assert "老师" in mask("老师说要注意")


def test_mask_hospital_landline_replaced() -> None:
    out = mask("联系电话 010-88886666 转 3")
    assert "010-88886666" not in out


def test_detect_kinds_ordered_and_deduped() -> None:
    kinds = detect_kinds("身份证 11010119900307891X 电话 13800138000 邮箱 a@b.com")
    assert kinds == ["id_card", "phone", "email"]


def test_detect_phi_leak_returns_first_kind() -> None:
    assert detect_phi_leak("手机 13800138000") == "phone"
    assert detect_phi_leak("没有敏感信息") is None
    assert detect_phi_leak("模型输出了 [PHI] 占位符") == "phi_marker_residual"


# --------------------------------------------------------------------------
# 入口中间件
# --------------------------------------------------------------------------


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
