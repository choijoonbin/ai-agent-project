# server/workflow/agents/jd_agent.py

from __future__ import annotations
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from workflow.state import InterviewState, AgentType
from workflow.agents.base_agent import BaseAgent

class JDAnalyzerAgent(BaseAgent):
    """
    JD(채용 공고)를 분석하는 에이전트.
    - JD 요약
    - 요구 역량/기술 목록 추출
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
                "당신은 채용 공고(JD)를 분석하는 HR 전문가입니다. "
                "핵심 요구 역량/기술/경험을 명확하게 추출해야 합니다."
            ),
            role=AgentType.JD_ANALYZER,
            use_rag=use_rag,
            k=k,
            use_mini=use_mini,
            session_id=session_id,
        )

    def run(self, state: InterviewState) -> InterviewState:
        jd_text = state["jd_text"]
        job_title = state["job_title"]

        # RAG 컨텍스트 구축 (선택)
        rag_context = self._build_rag_context(
            state,
            query=f"{job_title} 채용 공고 핵심 역량 및 역할",
        )

        system_prompt = self.system_prompt
        user_prompt = f"""
다음은 '{job_title}' 포지션에 대한 채용 공고(JD)입니다.

[JD 원문]
{jd_text}

[추가 참고 정보 (선택)]
{rag_context}

위 정보를 기반으로 다음과 같이 분석해주세요:

1) JD 핵심 요약 (3~5문장)
2) 요구되는 역량/기술/경험을 항목별 리스트로 정리
   - 형식 예시:
     - 역량: 문제해결 능력
     - 기술: Python, FastAPI
     - 경험: 3년 이상의 웹 서비스 개발 경험

응답은 다음 형식을 지켜주세요:

[JD 요약]
...

[요구 역량/기술/경험]
- ...
- ...
- ...
        """.strip()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        from utils.config import get_llm, get_langfuse_handler

        llm = get_llm(use_mini=self.use_mini, streaming=False)
        handler = get_langfuse_handler(session_id=self.session_id)

        if handler:
            response = llm.invoke(messages, config={"callbacks": [handler]})
        else:
            response = llm.invoke(messages)

        content = response.content

        # 아주 단순한 파싱: [JD 요약] / [요구 역량...] 구분
        summary = ""
        requirements: list[str] = []

        current_section: str | None = None
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("[JD 요약]"):
                current_section = "summary"
                continue
            if line.startswith("[요구 역량") or line.startswith("[요구 역량/기술/경험"):
                current_section = "requirements"
                continue

            if current_section == "summary":
                summary += line + "\n"
            elif current_section == "requirements":
                # "- " 또는 "• " 로 시작하면 리스트 항목으로 간주
                if line.startswith(("-", "•")):
                    req_text = line.lstrip("-• ").strip()
                    if req_text:
                        requirements.append(req_text)

        if not summary:
            summary = content  # 파싱 실패 시 전체 응답을 요약으로 사용

        state["jd_summary"] = summary.strip()
        state["jd_requirements"] = requirements
        state["status"] = "ANALYZING"
        state["prev_agent"] = self.role

        return state
