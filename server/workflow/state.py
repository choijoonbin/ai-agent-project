# server/workflow/state.py

"""
LangGraph에서 사용하는 공용 상태(State) 정의 모듈입니다.

면접 플로우는 대략 아래와 같은 단계를 거칩니다.

1) JD_ANALYZER_AGENT
   - JD 텍스트를 분석하여 요구 역량/기술/경험을 구조화

2) RESUME_ANALYZER_AGENT
   - 이력서 텍스트를 분석하여 후보의 경험/스킬/경력을 구조화
   - JD와의 매칭 포인트/미스매치 포인트 도출

3) INTERVIEWER_AGENT (멀티턴)
   - JD 분석 + 이력서 분석 + RAG 컨텍스트 기반으로
   - 맞춤형 면접 질문 생성
   - 사용자의 답변을 받아 qa_history에 축적

4) JUDGE_AGENT
   - JD 요약, 후보 요약, qa_history, RAG 문서를 모두 활용하여
   - 최종 평가 리포트/점수/추천 여부 생성
"""

from typing import Dict, List, TypedDict, Literal, Optional, Any


class AgentType:
    """
    LangGraph 상에서 각 노드(에이전트)를 구분하기 위한 역할 상수.
    """

    JD_ANALYZER = "JD_ANALYZER_AGENT"
    RESUME_ANALYZER = "RESUME_ANALYZER_AGENT"
    INTERVIEWER = "INTERVIEWER_AGENT"
    JUDGE = "JUDGE_AGENT"

    @classmethod
    def to_korean(cls, role: str) -> str:
        """
        UI/로그에 사용할 한글 역할명 매핑.
        """
        if role == cls.JD_ANALYZER:
            return "JD 분석 에이전트"
        if role == cls.RESUME_ANALYZER:
            return "이력서 분석 에이전트"
        if role == cls.INTERVIEWER:
            return "면접관 에이전트"
        if role == cls.JUDGE:
            return "평가 에이전트"
        return role


# 면접 진행 상태 값들
InterviewStatus = Literal[
    "INIT",         # 초기 상태
    "ANALYZING",    # JD/이력서 분석 중
    "INTERVIEW",    # 인터뷰(질문/답변) 진행 중
    "EVALUATING",   # 최종 평가 생성 중
    "DONE",         # 전체 플로우 완료
]


class QATurn(TypedDict, total=False):
    """
    면접 질문/답변 한 턴(turn)에 대한 구조.
    - interviewer: 어떤 에이전트/면접관이 질문했는지 (예: "INTERVIEWER_AGENT")
    - question: 질문 내용
    - answer: 지원자 답변 (Streamlit 쪽에서 입력 받은 텍스트)
    - category: 질문 카테고리 (예: "기술", "문화적합", "경험", "리더십" 등)
    - score: (선택) 이 턴에 대한 점수/평가 점수
    - notes: (선택) 내부용 메모/코멘트
    """
    interviewer: str
    question: str
    answer: str
    category: Optional[str]
    score: Optional[float]
    notes: Optional[str]


class EvaluationResult(TypedDict, total=False):
    """
    최종 평가 결과 구조.
    - summary: 전체 면접 요약
    - strengths: 강점 리스트
    - weaknesses: 약점 리스트
    - recommendation: 최종 추천 (예: "Strong Hire", "Hire", "No Hire")
    - scores: 역량별 점수 {"커뮤니케이션": 4.5, "문제해결": 4.0, ...}
    - detailed_scores: 직군별 세분화된 역량 점수 (예: {"프로젝트 계획 및 일정 관리": 22.5/30, ...})
    - career_transition: 전환 가능성 분석 및 제안
    - raw_text: LLM이 생성한 원문 평가 텍스트
    """
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    recommendation: str
    scores: Dict[str, float]
    detailed_scores: Dict[str, Dict[str, float]]  # {"역량명": {"점수": 22.5, "배점": 30, "비율": 0.75}}
    career_transition: Dict[str, Any]  # {"가능성": "높음/보통/낮음", "점수": 3.5, "제안": ["...", ...]}
    raw_text: str


class InterviewState(TypedDict):
    """
    LangGraph 전역 상태.
    모든 에이전트가 이 상태를 읽고/업데이트하면서 협력합니다.
    """

    # ===== 기본 정보 =====
    job_title: str                     # 채용 포지션명 (예: "백엔드 개발자")
    candidate_name: str                # 지원자 이름 (예: "홍길동")
    jd_text: str                       # JD 원문 텍스트
    resume_text: str                   # 이력서 원문 텍스트
    job_role: str                      # 직군/직무 태그 (예: "pm", "frontend", "general")

    # ===== 분석 결과 =====
    jd_summary: str                    # JD 분석/요약 결과
    jd_requirements: List[str]         # JD에서 추출한 요구 역량/기술 리스트
    candidate_summary: str             # 이력서 요약 (핵심 경력/프로젝트)
    candidate_skills: List[str]        # 이력서에서 추출된 기술 스택 리스트

    # ===== 인터뷰 진행 상태 =====
    qa_history: List[QATurn]           # 질문/응답 턴 로그
    current_question_index: int        # 현재까지 진행된 질문 수
    total_questions: int               # 계획된 총 질문 수
    status: InterviewStatus            # 현재 전체 플로우 상태
    prev_agent: str                    # 직전에 실행된 에이전트 역할 (AgentType.*)

    # ===== RAG 컨텍스트 =====
    # 각 에이전트가 RAG를 사용해 가져온 컨텍스트/문서들을 저장
    rag_contexts: Dict[str, str]       # {AgentType.*: 컨텍스트 텍스트}
    rag_docs: Dict[str, List[Any]]     # {AgentType.*: [원본 Document/page_content 리스트 등]}
    web_search_info: Dict[str, Any]    # {AgentType.*: {"used": bool, "query": str, "results_count": int, "results": List[Dict], "processing": str}}

    # ===== 최종 평가 결과 =====
    evaluation: Optional[EvaluationResult]


def create_initial_state(
    job_title: str,
    candidate_name: str,
    jd_text: str,
    resume_text: str,
    total_questions: int = 5,
    job_role: str = "general",
) -> InterviewState:
    """
    그래프 시작 시 사용할 초기 상태를 생성합니다.
    FastAPI /workflow 인터페이스에서 이 함수를 호출하여
    LangGraph의 초기 state로 넘기게 됩니다.
    """
    return InterviewState(
        job_title=job_title,
        candidate_name=candidate_name,
        jd_text=jd_text,
        resume_text=resume_text,
        job_role=job_role,
        jd_summary="",
        jd_requirements=[],
        candidate_summary="",
        candidate_skills=[],
        qa_history=[],
        current_question_index=0,
        total_questions=total_questions,
        status="INIT",
        prev_agent="",
        rag_contexts={},
        rag_docs={},
        web_search_info={},
        evaluation=None,
    )
