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
    status: str | None = None,  # Application status 필터
    db: Session = Depends(get_db),
):
    """면접 이력 목록 조회 (최신순)."""
    from db.models import Application
    
    query = db.query(InterviewModel)
    
    # Application status 필터 적용
    if status:
        query = query.join(Application, InterviewModel.application_id == Application.id).filter(
            Application.status == status
        )
    
    interviews = (
        query
        .order_by(InterviewModel.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    # Application status 정보 추가
    result = []
    for interview in interviews:
        interview_dict = InterviewSchema.model_validate(interview).model_dump()
        
        # application_id가 있으면 직접 조회
        if interview.application_id:
            app = db.query(Application).filter(Application.id == interview.application_id).first()
            if app:
                interview_dict["application_status"] = app.status
                interview_dict["application_id"] = app.id
        else:
            # application_id가 없으면 candidate_name으로 매칭 시도
            # 같은 이름의 지원자 중 가장 최근 Application 찾기
            from db.models import Member
            member = db.query(Member).filter(Member.name == interview.candidate_name).first()
            if member:
                # 해당 멤버의 가장 최근 Application 찾기
                app = (
                    db.query(Application)
                    .filter(Application.member_id == member.id)
                    .order_by(Application.updated_at.desc())
                    .first()
                )
                if app:
                    interview_dict["application_status"] = app.status
                    interview_dict["application_id"] = app.id
                    # application_id도 업데이트 (선택적)
                    interview.application_id = app.id
        
        result.append(InterviewSchema(**interview_dict))
    
    # application_id 업데이트가 있었다면 커밋
    try:
        db.commit()
    except:
        db.rollback()
    
    return result


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
