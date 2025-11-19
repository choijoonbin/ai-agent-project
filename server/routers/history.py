# server/routers/history.py

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Interview as InterviewModel
from db.schemas import InterviewSchema, InterviewCreate

router = APIRouter(
    prefix="/api/v1/interviews",
    tags=["interviews"],
)


@router.get("/", response_model=List[InterviewSchema])
def list_interviews(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """면접 이력 목록 조회 (최신순)."""
    interviews = (
        db.query(InterviewModel)
        .order_by(InterviewModel.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return interviews


@router.get("/{interview_id}", response_model=InterviewSchema)
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db),
):
    """특정 면접 이력 상세 조회."""
    interview = (
        db.query(InterviewModel)
        .filter(InterviewModel.id == interview_id)
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.post("/", response_model=InterviewSchema)
def create_interview(
    interview: InterviewCreate,
    db: Session = Depends(get_db),
):
    """새 면접 이력 저장 (내부적으로도 사용 가능)."""
    db_obj = InterviewModel(**interview.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/{interview_id}")
def delete_interview(
    interview_id: int,
    db: Session = Depends(get_db),
):
    """특정 면접 이력 삭제."""
    interview = (
        db.query(InterviewModel)
        .filter(InterviewModel.id == interview_id)
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    db.delete(interview)
    db.commit()
    return {"detail": "Interview deleted"}
