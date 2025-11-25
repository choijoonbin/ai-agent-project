# server/workflow/agents/resume_agent.py

from __future__ import annotations

from typing import List

from langchain_core.messages import SystemMessage, HumanMessage

from workflow.state import InterviewState, AgentType
from workflow.agents.base_agent import BaseAgent
from utils.config import get_llm, get_langfuse_handler


class ResumeAnalyzerAgent(BaseAgent):
    """
    이력서를 분석하여 후보의 요약/핵심 스킬/경험을 추출하는 에이전트.
    JD 요구사항과의 매칭 포인트도 간단히 파악합니다.
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
                "당신은 이력서를 분석하는 채용 담당자입니다. "
                "후보의 강점, 핵심 경험, 기술 스택을 정리하고 JD와의 적합도를 간단히 평가하세요."
            ),
            role=AgentType.RESUME_ANALYZER,
            use_rag=use_rag,
            k=k,
            use_mini=use_mini,
            session_id=session_id,
        )

    def run(self, state: InterviewState) -> InterviewState:
        resume_text = state["resume_text"]
        jd_summary = state["jd_summary"]
        jd_requirements = state["jd_requirements"]
        candidate_name = state["candidate_name"]
        job_title = state.get("job_title", "")
        job_role = state.get("job_role", "general")

        # 직군별 평가 기준을 포함한 RAG 컨텍스트 구축
        # 다른 직군 경험과의 차이점을 포함하여 정확한 분석을 위해 키워드 추가
        rag_context = self._build_rag_context(
            state,
            query=f"{job_title} {job_role} 이력서 평가 기준 역량 분석 다른 직군 경험과의 차이점",
        )

        system_prompt = self.system_prompt
        user_prompt = f"""
다음은 지원자 '{candidate_name}'의 이력서 내용입니다.

[이력서]
{resume_text}

[JD 요약]
{jd_summary}

[JD 요구 역량/기술/경험]
{chr(10).join(['- ' + r for r in jd_requirements])}

[추가 참고 정보 (직군별 평가 기준)]
{rag_context}

**중요 분석 원칙:**
- 지원자의 현재 직군 경험과 목표 직군({job_title})의 요구사항을 구분하여 분석하세요.
- 이력서 요약 시 지원자의 실제 직군 배경을 명확히 명시하세요 (예: "Backend 개발자", "Frontend 개발자", "PM" 등).
- JD 요구사항과의 적합도 평가 시, 지원자의 경험이 목표 직군 역량과 직접적으로 매칭되는지 신중히 판단하세요.

위 정보를 기반으로 다음을 작성해주세요:

1) 지원자 이력 요약 (3~5문장)
2) 핵심 기술 스택 리스트 (예: Python, FastAPI, AWS, ...)
3) JD 요구사항과의 적합도에 대한 간단한 코멘트 (2~3문장)

응답 형식:

[이력서 요약]
...

[핵심 기술]
- 기술1
- 기술2
...

[적합도 코멘트]
...
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

        summary = ""
        skills: List[str] = []

        current_section: str | None = None
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("[이력서 요약]"):
                current_section = "summary"
                continue
            if line.startswith("[핵심 기술]"):
                current_section = "skills"
                continue
            if line.startswith("[적합도 코멘트]"):
                current_section = "comment"
                continue

            if current_section == "summary":
                summary += line + "\n"
            elif current_section == "skills":
                if line.startswith(("-", "•")):
                    skill = line.lstrip("-• ").strip()
                    if skill:
                        skills.append(skill)

        if not summary:
            summary = content

        state["candidate_summary"] = summary.strip()
        state["candidate_skills"] = skills
        state["status"] = "ANALYZING"
        state["prev_agent"] = self.role

        return state
