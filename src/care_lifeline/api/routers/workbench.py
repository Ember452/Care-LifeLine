from __future__ import annotations

import contextlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from care_lifeline.api.security import (
    ROLE_ADMIN,
    ROLE_CLINICIAN,
    CurrentUser,
    require_roles,
)
from care_lifeline.db import session_store
from care_lifeline.eval.promote import promote_review

router = APIRouter(prefix="/v1/workbench", tags=["workbench"])

# /v1/workbench/* 仅 clinician / admin（契约 §6）。
_require_clinician = require_roles(ROLE_CLINICIAN, ROLE_ADMIN)


class ReviewItem(BaseModel):
    id: int
    thread_id: str
    status: str
    input_text: str
    draft: str
    qc: dict
    violations: list
    patient_context: str | None
    reviewer: str | None
    decision: str | None
    corrected_text: str | None


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject|edit|revise)$")
    corrected_text: str | None = None


def _to_item(review) -> ReviewItem:
    return ReviewItem(
        id=review.id,
        thread_id=review.thread_id,
        status=review.status,
        input_text=review.input_text,
        draft=review.draft,
        qc=json.loads(review.qc_json or "{}"),
        violations=json.loads(review.violations_json or "[]"),
        patient_context=review.patient_context,
        reviewer=review.reviewer,
        decision=review.decision,
        corrected_text=review.corrected_text,
    )


@router.get("/queue", response_model=list[ReviewItem], dependencies=[Depends(_require_clinician)])
def queue() -> list[ReviewItem]:
    return [_to_item(r) for r in session_store.list_pending_reviews()]


@router.get(
    "/items/{review_id}",
    response_model=ReviewItem,
    dependencies=[Depends(_require_clinician)],
)
def item(review_id: int) -> ReviewItem:
    review = session_store.get_review(review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "审核项不存在"},
        )
    return _to_item(review)


@router.post("/items/{review_id}/review", response_model=ReviewItem)
def review(
    review_id: int,
    body: ReviewDecision,
    user: Annotated[CurrentUser, Depends(_require_clinician)],
) -> ReviewItem:
    """审核并解决一条 HITL 队列项（P2-17：审核结果自动沉淀进评测反馈集）。"""
    if body.decision in ("edit", "revise") and not body.corrected_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_request", "message": "edit/revise 需提供 corrected_text"},
        )
    resolved = session_store.resolve_review(
        review_id, body.decision, user.username, body.corrected_text
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "审核项不存在"},
        )
    session_store.write_audit(resolved.session_id, f"hitl_review_{body.decision}", user.username)
    if body.decision == "edit":
        session_store.append_clinician_message(resolved.session_id, body.corrected_text or "")
    # 数据飞轮：审核定稿自动沉淀为评测反馈样本（P2-17）。
    with contextlib.suppress(Exception):
        promote_review(resolved)
    return _to_item(resolved)
