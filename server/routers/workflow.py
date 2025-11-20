# server/routers/workflow.py

from __future__ import annotations

import json
import uuid
from typing import Any, List, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workflow.state import InterviewState, create_initial_state
from workflow.graph import create_interview_graph
from utils.config import get_langfuse_handler, get_llm
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
        config = {
            "callbacks": [langfuse_handler],
            "configurable": {
                "thread_id": session_id,
            },
            "tags": [f"session:{session_id}", "interview_workflow"],
        }
        final_state = graph.invoke(initial_state, config=config)

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"LangGraph 실행 완료. Langfuse Session ID: {session_id}")
        logger.info(
            f"Langfuse 대시보드에서 세션 '{session_id}' 또는 태그 'interview_workflow'로 검색하세요."
        )
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
    is_followup: bool | None = None
    parent_index: int | None = None


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

    # qa_history 교체 + 평가 초기화
    state["qa_history"] = [qa.model_dump() for qa in request.qa_history]
    state["evaluation"] = None
    state["status"] = "INTERVIEW"

    # JudgeAgent 실행
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

    # DB에 업데이트된 state_json 저장
    interview.state_json = json.dumps(state_dict, ensure_ascii=False)
    interview.status = state_dict.get("status", "DONE")
    db.add(interview)
    db.commit()

    return RejudgeResponse(
        status="success",
        state=state_dict,
        interview_id=interview.id,
    )


# ========== 3) Insights 생성 엔드포인트 ========== #

class InterviewInsightsRequest(BaseModel):
    interview_id: int
    use_mini: bool = True


class InterviewInsightsResponse(BaseModel):
    status: str
    interview_id: int
    insights: Dict[str, Any]


@router.post("/interview/insights", response_model=InterviewInsightsResponse)
def generate_interview_insights(
    request: InterviewInsightsRequest,
    db: Session = Depends(get_db),
) -> InterviewInsightsResponse:
    """
    저장된 인터뷰(state_json)를 기반으로
    - Soft-landing 플랜
    - 조직 기여도/성장 잠재력 스코어
    - 리스크 및 케어포인트
    - 성장/온보딩 추천
    등을 LLM으로 생성하는 엔드포인트.
    """

    interview: InterviewModel | None = (
        db.query(InterviewModel)
        .filter(InterviewModel.id == request.interview_id)
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    try:
        state: dict[str, Any] = json.loads(interview.state_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Saved state_json is corrupted or invalid.",
        )

    job_title = interview.job_title
    candidate_name = interview.candidate_name
    jd_text = interview.jd_text or ""
    resume_text = interview.resume_text or ""
    evaluation = state.get("evaluation", {})
    qa_history = state.get("qa_history", [])

    # LLM 호출 준비
    llm = get_llm(use_mini=request.use_mini, streaming=False)

    # 프롬프트: JSON 형식으로만 답변하도록 강제
    system_prompt = """
당신은 채용 담당자와 현업 리더를 돕는 HR/조직 컨설팅 전문가입니다.
입력으로 주어진 JD, 후보자의 이력, 면접 평가 내용을 바탕으로
"채용 후 90일 온보딩 전략"과 "조직 기여도/성장 잠재력"을 분석합니다.

반드시 JSON만 출력해야 하며, 설명 문구를 JSON 바깥에 추가하면 안 됩니다.
JSON 스키마는 다음과 같습니다:

{
  "soft_landing_plan": "입사 후 90일 동안 어떤 식으로 온보딩/학습/적응을 지원하면 좋은지에 대한 구체적인 제안 (한국어, 문단 형태)",
  "contribution_summary": "이 후보자가 팀/조직에 어떤 방식으로 기여할 수 있을지에 대한 요약 (한국어)",
  "contribution_scores": {
    "short_term_impact": 1~5 정수 또는 실수,
    "long_term_growth": 1~5,
    "team_fit": 1~5,
    "risk_level": 1~5  // 숫자가 높을수록 리스크가 크다는 의미
  },
  "risk_factors": [
    "리스크 또는 주의해야 할 점 항목 (문장)",
    "..."
  ],
  "growth_recommendations": [
    "성장을 위해 회사/리더가 제공하면 좋은 지원/코칭/환경에 대한 제안",
    "..."
  ]
}
    """.strip()

    # context를 하나의 큰 문자열로 구성
    context = {
        "job_title": job_title,
        "candidate_name": candidate_name,
        "jd_text": jd_text,
        "resume_text": resume_text,
        "evaluation": evaluation,
        "qa_history": qa_history,
    }

    user_prompt = (
        "다음은 한 후보자의 채용 인터뷰 관련 전체 컨텍스트입니다.\n\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "위 정보를 바탕으로 앞서 설명한 JSON 스키마에 맞게 인사이트를 생성해 주세요."
    )

    # LangChain 스타일 without explicit callbacks (안전하게 최소 호출)
    from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    raw_content = getattr(response, "content", "") if response is not None else ""

    # JSON 파싱 시도
    try:
        insights_obj = json.loads(raw_content)
        if not isinstance(insights_obj, dict):
            raise ValueError("Insights is not a JSON object")
    except Exception:
        # 실패 시 raw 텍스트를 그대로 넘김
        insights_obj = {
            "soft_landing_plan": "",
            "contribution_summary": "",
            "contribution_scores": {},
            "risk_factors": [],
            "growth_recommendations": [],
            "raw_text": raw_content,
        }

    return InterviewInsightsResponse(
        status="success",
        interview_id=interview.id,
        insights=insights_obj,
    )
