# server/db/models.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.database import Base


class Interview(Base):
    """
    하나의 면접 실행 결과를 저장하는 테이블.

    - job_title: 채용 포지션
    - candidate_name: 지원자 이름
    - total_questions: 준비된 질문 개수
    - status: 최종 상태 (INIT/ANALYZING/INTERVIEW/DONE 등)
    - state_json: LangGraph 최종 state 전체를 JSON 문자열로 저장
    - application_id: 연결된 지원서 ID (선택적)
    """

    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String(255), nullable=False)
    candidate_name = Column(String(255), nullable=False)
    total_questions = Column(Integer, nullable=False, default=5)
    status = Column(String(50), nullable=False, default="DONE")
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)

    jd_text = Column(Text, nullable=False)
    resume_text = Column(Text, nullable=False)

    state_json = Column(Text, nullable=False)  # LangGraph 최종 상태를 JSON 문자열로
    video_path = Column(String(1024), nullable=True)  # 면접 녹화 영상 경로

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    application = relationship(
        "Application",
        foreign_keys=[application_id],
    )


class Member(Base):
    """
    지원자/관리자 회원 테이블.
    - role: ADMIN | NORMAL
    """

    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    birth = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False, default="NORMAL")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    applications = relationship("Application", back_populates="member")


class Recruitment(Base):
    """
    채용공고 메타 데이터.
    - file_path: 원본 JD 문서 경로 (server/data/recruitment/ 아래)
    """

    __tablename__ = "recruitments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    company = Column(String(255), nullable=False, default="미정")
    location = Column(String(255), nullable=True)
    employment_type = Column(String(50), nullable=True)  # 정규/계약 등
    experience_level = Column(String(50), nullable=True)  # 신입/경력/무관
    role_category = Column(String(255), nullable=True)  # 직무/카테고리
    job_family = Column(String(255), nullable=True)  # 직군/직렬
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    deadline = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="OPEN")  # OPEN/CLOSED/ARCHIVED
    summary = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    first_line = Column(String(500), nullable=True)
    keywords = Column(Text, nullable=True)  # JSON 직렬화
    file_path = Column(String(1024), nullable=False)
    posted_by = Column(Integer, nullable=True)  # 업로더 ID

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    applications = relationship(
        "Application",
        back_populates="recruitment",
        foreign_keys="Application.recruitment_id",
    )


class Application(Base):
    """
    지원 이력 테이블.
    - status: IN_PROGRESS/SUBMITTED/PASSED/REJECTED
    """

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    recruitment_id = Column(Integer, ForeignKey("recruitments.id"), nullable=False)
    first_choice_id = Column(Integer, ForeignKey("recruitments.id"), nullable=False)
    second_choice_id = Column(Integer, ForeignKey("recruitments.id"), nullable=True)

    mbti = Column(String(20), nullable=True)
    cover_letter = Column(Text, nullable=True)
    resume_path = Column(String(1024), nullable=False)

    status = Column(String(20), nullable=False, default="IN_PROGRESS")
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    member = relationship(
        "Member",
        back_populates="applications",
        foreign_keys=[member_id],
    )
    recruitment = relationship(
        "Recruitment",
        back_populates="applications",
        foreign_keys=[recruitment_id],
    )
    first_choice = relationship(
        "Recruitment",
        foreign_keys=[first_choice_id],
        viewonly=True,
    )
    second_choice = relationship(
        "Recruitment",
        foreign_keys=[second_choice_id],
        viewonly=True,
    )
