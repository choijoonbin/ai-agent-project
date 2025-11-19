# server/db/schemas.py

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InterviewBase(BaseModel):
    job_title: str
    candidate_name: str
    total_questions: int
    status: str
    jd_text: str
    resume_text: str
    state_json: str


class InterviewCreate(InterviewBase):
    pass


class InterviewSchema(InterviewBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True  # SQLAlchemy 모델 → Pydantic 변환
