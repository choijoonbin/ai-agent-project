# server/db/models.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime
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
    """

    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String(255), nullable=False)
    candidate_name = Column(String(255), nullable=False)
    total_questions = Column(Integer, nullable=False, default=5)
    status = Column(String(50), nullable=False, default="DONE")

    jd_text = Column(Text, nullable=False)
    resume_text = Column(Text, nullable=False)

    state_json = Column(Text, nullable=False)  # LangGraph 최종 상태를 JSON 문자열로

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
