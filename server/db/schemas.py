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


# -------- Members -------- #


class MemberBase(BaseModel):
    name: str
    birth: str  # YYYY-MM-DD


class MemberCreate(MemberBase):
    role: str = "NORMAL"


class MemberSchema(MemberBase):
    id: int
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# -------- Recruitments -------- #


class RecruitmentBase(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    role_category: str | None = None
    deadline: str | None = None
    status: str = "OPEN"
    summary: str | None = None
    file_path: str
    raw_text: str | None = None
    first_line: str | None = None
    experience_badge: str | None = None
    location_badge: str | None = None
    requirement_keywords: list[str] | None = None


class RecruitmentCreate(RecruitmentBase):
    pass


class RecruitmentSchema(RecruitmentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# -------- Applications -------- #


class ApplicationBase(BaseModel):
    member_id: int
    recruitment_id: int
    first_choice_id: int
    second_choice_id: int | None = None
    mbti: str | None = None
    cover_letter: str | None = None
    resume_path: str
    status: str = "IN_PROGRESS"


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationSchema(ApplicationBase):
    id: int
    submitted_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ApplicationWithMeta(BaseModel):
    id: int
    member_id: int
    member_name: str
    member_birth: str
    recruitment_id: int
    recruitment_title: str | None = None
    recruitment_first_line: str | None = None
    status: str
    submitted_at: datetime | None = None
    resume_path: str | None = None
