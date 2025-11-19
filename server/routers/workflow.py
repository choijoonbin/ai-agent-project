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
from utils.config import get_langfuse_handler, get_llm
from db.database import get_db
from db.models import Interview as InterviewModel
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
        config = {
            "callbacks": [langfuse_handler],
            "configurable": {
                "thread_id": session_id,
            },
            "tags": [f"session:{session_id}", "interview_workflow"],
        }
        final_state = graph.invoke(initial_state, config=config)
    else:
        final_state = graph.invoke(initial_state)

    state_dict: dict[str, Any] = dict(final_state)

    interview_id: int | None = None

    if request.save_history:
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

    state["qa_history"] = [qa.model_dump() for qa in request.qa_history]
    state["evaluation"] = None
    state["status"] = "INTERVIEW"

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

    interview.state_json = json.dumps(state_dict, ensure_ascii=False)
    interview.status = state_dict.get("status", "DONE")
    db.add(interview)
    db.commit()

    return RejudgeResponse(
        status="success",
        state=state_dict,
        interview_id=interview.id,
    )


# ========== 3) 질문별 후속 질문(재질문) 생성 ========== #

class FollowupRequest(BaseModel):
    interview_id: int
    question: str
    answer: str
    category: str | None = None
    use_mini: bool = True


class FollowupResponse(BaseModel):
    followup_question: str


@router.post("/interview/followup", response_model=FollowupResponse)
def generate_followup_question(
    request: FollowupRequest,
    db: Session = Depends(get_db),
) -> FollowupResponse:
    """
    특정 질문/답변 쌍에 대해,
    '이 답변을 더 깊게 파는 후속 질문'을 1개 생성하는 엔드포인트.
    상태는 변경하지 않고, 질문만 반환.
    """
    interview: InterviewModel | None = (
        db.query(InterviewModel)
        .filter(InterviewModel.id == request.interview_id)
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    llm = get_llm(use_mini=request.use_mini, streaming=False)

    job_title = interview.job_title
    category = request.category or "일반"

    prompt = f"""
당신은 '{job_title}' 포지션의 시니어 기술 면접관입니다.

아래는 이전에 던진 질문과, 지원자의 답변입니다.
이 답변을 더 깊이 파고, 실무 역량을 검증하기 위한 **후속 질문** 1개를 한국어로 작성하세요.

- 질문 카테고리: {category}
- 형식: 한 문장, 최대 150자 이내
- 지나치게 포괄적인 질문은 피하고, 구체적인 경험/사례/방법을 물어보세요.

[이전 질문]
{request.question}

[지원자 답변]
{request.answer}
"""

    resp = llm.invoke(prompt)
    followup = resp.content.strip()

    return FollowupResponse(followup_question=followup)
