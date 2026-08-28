from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.db import session_store

router = APIRouter(prefix="/v1/workbench", tags=["workbench"])


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
    decision: str  # approve | reject | edit
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


@router.get("/queue", response_model=list[ReviewItem])
def queue(user: CurrentUser = Depends(get_current_user)) -> list[ReviewItem]:
    return [_to_item(r) for r in session_store.list_pending_reviews()]


@router.get("/items/{review_id}", response_model=ReviewItem)
def item(review_id: int, user: CurrentUser = Depends(get_current_user)) -> ReviewItem:
    review = session_store.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核项不存在")
    return _to_item(review)


@router.post("/items/{review_id}/review", response_model=ReviewItem)
def review(
    review_id: int, body: ReviewDecision, user: CurrentUser = Depends(get_current_user)
) -> ReviewItem:
    if body.decision not in ("approve", "reject", "edit"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision 必须为 approve/reject/edit",
        )
    if body.decision == "edit" and not body.corrected_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="edit 需提供 corrected_text"
        )
    resolved = session_store.resolve_review(
        review_id, body.decision, user.username, body.corrected_text
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核项不存在")
    session_store.write_audit(
        resolved.session_id, f"hitl_review_{body.decision}", user.username
    )
    if body.decision == "edit":
        session_store.append_clinician_message(resolved.session_id, body.corrected_text or "")
    return _to_item(resolved)
