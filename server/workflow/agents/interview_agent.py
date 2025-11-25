# server/workflow/agents/interview_agent.py

from __future__ import annotations

from typing import List

from langchain_core.messages import SystemMessage, HumanMessage

from workflow.state import InterviewState, AgentType, QATurn
from workflow.agents.base_agent import BaseAgent
from utils.config import get_llm, get_langfuse_handler


class InterviewerAgent(BaseAgent):
    """
    JD + 이력서 + RAG 컨텍스트를 기반으로
    맞춤형 면접 질문 리스트를 생성하는 에이전트.

    현재 버전에서는 질문만 자동 생성하고, 답변은 빈 문자열로 두며
    나중에 UI에서 사용자가 직접 채워 넣을 수 있는 구조입니다.
    """

    def __init__(
        self,
        use_rag: bool = True,
        k: int = 3,
        use_mini: bool = True,
        session_id: str | None = None,
    ) -> None:
        super().__init__(
            system_prompt=(
                "당신은 구조화된 인터뷰를 진행하는 시니어 면접관입니다. "
                "핵심 역량을 검증할 수 있는 구체적인 질문을 생성하세요."
            ),
            role=AgentType.INTERVIEWER,
            use_rag=use_rag,
            k=k,
            use_mini=use_mini,
            session_id=session_id,
        )

    def run(self, state: InterviewState) -> InterviewState:
        job_title = state["job_title"]
        candidate_name = state["candidate_name"]
        jd_summary = state["jd_summary"]
        jd_requirements = state["jd_requirements"]
        candidate_summary = state["candidate_summary"]
        candidate_skills = state["candidate_skills"]
        total_questions = state["total_questions"]

        # RAG 검색 쿼리 개선: 역량 차이점을 고려한 질문 생성을 위해 키워드 추가
        rag_context = self._build_rag_context(
            state,
            query=f"{job_title} {state.get('job_role', 'general')} 인터뷰 질문 예시 평가 기준 역량 차이점",
        )

        system_prompt = self.system_prompt
        user_prompt = f"""
당신은 '{job_title}' 포지션에 대한 면접관입니다.
지원자 이름은 '{candidate_name}'입니다.

[JD 요약]
{jd_summary}

[JD 요구 역량/기술/경험]
{chr(10).join(['- ' + r for r in jd_requirements])}

[지원자 이력 요약]
{candidate_summary}

[지원자의 핵심 기술]
{', '.join(candidate_skills) if candidate_skills else '(기술 정보 없음)'}

[추가 참고 정보 (RAG)]
{rag_context}

위 정보를 바탕으로 총 {total_questions}개의 면접 질문을 만들어주세요.

요구사항:
- 각 질문은 하나의 명확한 역량 또는 경험을 타겟으로 할 것
- 행동 기반 질문(BEHAVIORAL QUESTION)을 우선적으로 생성 (예: 과거 사례 기반)
- 난이도는 중~상 수준
- 질문은 한국어로 작성

응답 형식:

[질문 리스트]
1. (카테고리: 기술) 질문 내용...
2. (카테고리: 협업) 질문 내용...
...

숫자와 카테고리, 질문 내용을 포함해서 출력해주세요.
        """.strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        llm = get_llm(use_mini=self.use_mini, streaming=False)
        handler = get_langfuse_handler(session_id=self.session_id)

        if handler:
            response = llm.invoke(messages, config={"callbacks": [handler]})
        else:
            response = llm.invoke(messages)

        content = response.content

        qa_list: List[QATurn] = []

        in_list = False
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("[질문 리스트]"):
                in_list = True
                continue

            if not in_list:
                continue

            # 예: "1. (카테고리: 기술) 질문 내용..."
            if line[0].isdigit():
                # 번호 제거
                parts = line.split(".", 1)
                if len(parts) < 2:
                    continue
                rest = parts[1].strip()

                category = None
                question_text = rest

                # (카테고리: 기술) 패턴 파싱
                if rest.startswith("(") and "카테고리" in rest:
                    try:
                        cat_part, q_part = rest.split(")", 1)
                        if "카테고리:" in cat_part:
                            category = cat_part.split("카테고리:")[1].strip()
                        question_text = q_part.strip()
                    except ValueError:
                        pass

                qa_list.append(
                    QATurn(
                        interviewer=self.role,
                        question=question_text,
                        answer="",  # 초기에는 빈 문자열, UI에서 나중에 채울 수 있도록
                        category=category,
                        score=None,
                        notes=None,
                    )
                )

        # QA 히스토리에 추가
        state["qa_history"] = qa_list
        state["current_question_index"] = len(qa_list)
        state["status"] = "INTERVIEW"
        state["prev_agent"] = self.role

        return state
