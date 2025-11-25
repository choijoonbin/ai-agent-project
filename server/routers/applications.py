# server/routers/applications.py

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db import models, schemas
from utils.doc_loader import ensure_dir
from db import models

router = APIRouter(
    prefix="/api/v1/applications",
    tags=["applications"],
)

BASE_DIR = Path(__file__).resolve().parents[1]
RESUME_DIR = ensure_dir(BASE_DIR / "data" / "resumes")


ACTIVE_STATUSES = ["SUBMITTED", "DOCUMENT_REVIEW", "INTERVIEW"]


def _active_application(db: Session, member_id: int) -> models.Application | None:
    return (
        db.query(models.Application)
        .filter(
            models.Application.member_id == member_id,
            models.Application.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )


@router.post("/submit", response_model=schemas.ApplicationSchema)
async def submit_application(
    member_id: int = Form(...),
    recruitment_id: int = Form(...),
    first_choice_id: int = Form(...),
    second_choice_id: int | None = Form(None),
    mbti: str | None = Form(None),
    cover_letter: str | None = Form(None),
    resume: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> schemas.ApplicationSchema:
    member = db.query(models.Member).filter(models.Member.id == member_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # 한 건만 진행 가능
    active = _active_application(db, member_id)
    if active:
        raise HTTPException(
            status_code=400,
            detail="이미 진행 중인 지원이 있습니다. 결과 확정 후 다시 지원해주세요.",
        )

    rec = (
        db.query(models.Recruitment)
        .filter(models.Recruitment.id == recruitment_id, models.Recruitment.status == "OPEN")
        .first()
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="채용공고를 찾을 수 없습니다.")

    # 파일 저장
    ext = Path(resume.filename).suffix or ".bin"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = RESUME_DIR / filename
    content = await resume.read()
    save_path.write_bytes(content)

    app = models.Application(
        member_id=member_id,
        recruitment_id=recruitment_id,
        first_choice_id=first_choice_id,
        second_choice_id=second_choice_id,
        mbti=mbti,
        cover_letter=cover_letter,
        resume_path=str(save_path),
        status="SUBMITTED",
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.get("/my/{member_id}", response_model=List[schemas.ApplicationSchema])
def get_my_applications(member_id: int, db: Session = Depends(get_db)) -> List[schemas.ApplicationSchema]:
    apps = (
        db.query(models.Application)
        .filter(models.Application.member_id == member_id)
        .order_by(models.Application.submitted_at.desc())
        .all()
    )
    return apps


@router.get("/all", response_model=List[schemas.ApplicationWithMeta])
def list_all_applications(db: Session = Depends(get_db)) -> List[schemas.ApplicationWithMeta]:
    """
    관리자용: 전체 지원 목록 + 지원자/채용공고 메타.
    """
    rows = (
        db.query(
            models.Application,
            models.Member,
            models.Recruitment,
        )
        .join(models.Member, models.Application.member_id == models.Member.id)
        .join(models.Recruitment, models.Application.recruitment_id == models.Recruitment.id)
        .order_by(models.Application.submitted_at.desc())
        .all()
    )

    results: List[schemas.ApplicationWithMeta] = []
    for app_obj, mem, rec in rows:
        results.append(
            schemas.ApplicationWithMeta(
                id=app_obj.id,
                member_id=app_obj.member_id,
                member_name=mem.name,
                member_birth=mem.birth,
                recruitment_id=app_obj.recruitment_id,
                recruitment_title=rec.title,
                recruitment_first_line=getattr(rec, "first_line", None),
                status=app_obj.status,
                submitted_at=app_obj.submitted_at,
                resume_path=app_obj.resume_path,
            )
        )
    return results


class ApplicationStatusUpdate(BaseModel):
    status: str  # SUBMITTED | DOCUMENT_REVIEW | INTERVIEW | PASSED | REJECTED | CANCELLED


@router.patch("/{application_id}/status", response_model=schemas.ApplicationSchema)
def update_application_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
) -> schemas.ApplicationSchema:
    app_obj = db.query(models.Application).filter(models.Application.id == application_id).first()
    if app_obj is None:
        raise HTTPException(status_code=404, detail="Application not found")

    app_obj.status = payload.status
    db.add(app_obj)
    db.commit()
    db.refresh(app_obj)
    return app_obj
