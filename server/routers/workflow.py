# server/routers/workflow.py

from __future__ import annotations

import json
import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workflow.state import InterviewState, create_initial_state
from workflow.graph import create_interview_graph
from utils.config import get_langfuse_handler
from db.database import get_db
from db.models import Interview as InterviewModel
from db.schemas import InterviewSchema, InterviewCreate
from workflow.agents.judge_agent import JudgeAgent

router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
)


# ========== 1) 최초 면접 실행 ========== #

class InterviewRequest(BaseModel):
    job_title: str
    candidate_name: str
    jd_text: str
    resume_text: str
    total_questions: int = 5
    enable_rag: bool = True
    use_mini: bool = True
    save_history: bool = True  # 실행 시 자동 저장 여부


class InterviewResponse(BaseModel):
    status: str
    state: dict[str, Any]
    interview_id: int | None = None


@router.post("/interview/run", response_model=InterviewResponse)
def run_interview_workflow(
    request: InterviewRequest,
    db: Session = Depends(get_db),
) -> InterviewResponse:
    """
    LangGraph 기반 면접 플로우를 한 번 실행하고 최종 상태를 반환하는 엔드포인트.
    - save_history=True 인 경우, 결과를 DB(interviews 테이블)에 저장.
    """

    session_id = str(uuid.uuid4())

    graph = create_interview_graph(
        enable_rag=request.enable_rag,
        session_id=session_id,
        use_mini=request.use_mini,
    )

    initial_state: InterviewState = create_initial_state(
        job_title=request.job_title,
        candidate_name=request.candidate_name,
        jd_text=request.jd_text,
        resume_text=request.resume_text,
        total_questions=request.total_questions,
    )

    langfuse_handler = get_langfuse_handler(session_id=session_id)
    if langfuse_handler:
        # LangGraph에서 Langfuse를 사용하기 위한 config 설정
        # LangGraph는 configurable에 session_id를 포함할 수 있음
        config = {
            "callbacks": [langfuse_handler],
            "configurable": {
                "thread_id": session_id,  # LangGraph의 thread_id로 session 추적
            },
            "tags": [f"session:{session_id}", "interview_workflow"],  # Langfuse에서 필터링하기 위한 태그
        }
        final_state = graph.invoke(initial_state, config=config)
        
        # Langfuse에 데이터가 전송되었는지 확인을 위한 로그
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"LangGraph 실행 완료. Langfuse Session ID: {session_id}")
        logger.info(f"Langfuse 대시보드에서 세션 '{session_id}' 또는 태그 'interview_workflow'로 검색하세요.")
    else:
        final_state = graph.invoke(initial_state)

    # Pydantic에서 직렬화 가능하도록 dict로 변환
    state_dict: dict[str, Any] = dict(final_state)

    interview_id: int | None = None

    if request.save_history:
        # 최종 상태를 JSON 문자열로 저장
        state_json = json.dumps(state_dict, ensure_ascii=False)

        db_obj = InterviewModel(
            job_title=request.job_title,
            candidate_name=request.candidate_name,
            total_questions=request.total_questions,
            status=state_dict.get("status", "DONE"),
            jd_text=request.jd_text,
            resume_text=request.resume_text,
            state_json=state_json,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        interview_id = db_obj.id

    return InterviewResponse(
        status="success",
        state=state_dict,
        interview_id=interview_id,
    )


# ========== 2) 질문/답변 수정 후 Judge만 재실행 ========== #

class QATurnModel(BaseModel):
    interviewer: str
    question: str
    answer: str
    category: str | None = None
    score: float | None = None
    notes: str | None = None


class RejudgeRequest(BaseModel):
    interview_id: int
    qa_history: List[QATurnModel]
    enable_rag: bool = True
    use_mini: bool = True


class RejudgeResponse(BaseModel):
    status: str
    state: dict[str, Any]
    interview_id: int


@router.post("/interview/rejudge", response_model=RejudgeResponse)
def rejudge_interview(
    request: RejudgeRequest,
    db: Session = Depends(get_db),
) -> RejudgeResponse:
    """
    질문/답변(qa_history)을 수정한 뒤,
    JudgeAgent만 다시 실행해서 평가를 갱신하는 엔드포인트.
    """

    # 1) 기존 인터뷰 이력 로드
    interview: InterviewModel | None = (
        db.query(InterviewModel)
        .filter(InterviewModel.id == request.interview_id)
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    try:
        state: InterviewState = json.loads(interview.state_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Saved state_json is corrupted or invalid.",
        )

    # 2) qa_history만 새로 교체
    state["qa_history"] = [qa.model_dump() for qa in request.qa_history]
    # 이전 평가 결과는 초기화
    state["evaluation"] = None
    state["status"] = "INTERVIEW"

    # 3) JudgeAgent만 직접 실행
    session_id = str(uuid.uuid4())
    judge_agent = JudgeAgent(
        use_rag=request.enable_rag,
        k=3 if request.enable_rag else 0,
        use_mini=request.use_mini,
        session_id=session_id,
    )

    langfuse_handler = get_langfuse_handler(session_id=session_id)

    if langfuse_handler:
        new_state = judge_agent.run(state)
    else:
        new_state = judge_agent.run(state)

    state_dict: dict[str, Any] = dict(new_state)

    # 4) DB에 업데이트된 state_json 저장
    interview.state_json = json.dumps(state_dict, ensure_ascii=False)
    interview.status = state_dict.get("status", "DONE")
    db.add(interview)
    db.commit()

    return RejudgeResponse(
        status="success",
        state=state_dict,
        interview_id=interview.id,
    )