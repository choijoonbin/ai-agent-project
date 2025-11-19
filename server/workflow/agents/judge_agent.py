# server/workflow/agents/judge_agent.py

from __future__ import annotations

from typing import List

from langchain_core.messages import SystemMessage, HumanMessage

from workflow.state import InterviewState, AgentType, EvaluationResult
from workflow.agents.base_agent import BaseAgent
from utils.config import get_llm, get_langfuse_handler


class JudgeAgent(BaseAgent):
    """
    전체 면접 흐름(JD, 이력서, 질문 리스트, 답변 등)을 바탕으로
    최종 평가 리포트를 생성하는 에이전트.
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
                "당신은 공정하고 논리적인 채용 평가자입니다. "
                "지원자의 강점/약점, 역량별 평가, 최종 추천 여부를 명확하게 제시해야 합니다."
            ),
            role=AgentType.JUDGE,
            use_rag=use_rag,
            k=k,
            use_mini=use_mini,
            session_id=session_id,
        )

    def run(self, state: InterviewState) -> InterviewState:
        job_title = state["job_title"]
        candidate_name = state["candidate_name"]

        rag_context = self._build_rag_context(
            state,
            query=f"{job_title} 포지션 채용 평가 기준 및 역량 정의",
        )

        qa_lines: List[str] = []
        for i, turn in enumerate(state["qa_history"], start=1):
            qa_lines.append(
                f"Q{i}. [{turn.get('category')}] {turn['question']}\nA{i}. {turn.get('answer', '(답변 없음)')}"
            )

        qa_text = "\n\n".join(qa_lines)

        system_prompt = self.system_prompt
        user_prompt = f"""
당신은 이제 '{job_title}' 포지션에 지원한 '{candidate_name}'의 면접 평가를 작성해야 합니다.

[JD 요약]
{state['jd_summary']}

[JD 요구 역량/기술/경험]
{chr(10).join(['- ' + r for r in state['jd_requirements']])}

[지원자 이력 요약]
{state['candidate_summary']}

[지원자의 핵심 기술]
{', '.join(state['candidate_skills']) if state['candidate_skills'] else '(기술 정보 없음)'}

[면접 질문 및 답변]
{qa_text if qa_text else '(질문/답변 기록 없음)'}

[추가 참고 정보 (RAG)]
{rag_context}

위 정보를 바탕으로 다음을 포함하는 평가 리포트를 작성해주세요:

1) 전체 요약 (3~5문장)
2) 지원자의 주요 강점 리스트
3) 지원자의 주요 약점 리스트
4) 역량별 평가 점수 (예: 커뮤니케이션: 4/5, 문제해결: 3/5, 리더십: 2/5 ...)
5) 최종 추천 (예: Strong Hire / Hire / No Hire) 및 한 줄 코멘트

응답 형식 예시:

[요약]
...

[강점]
- ...

[약점]
- ...

[점수표]
- 커뮤니케이션: 4/5
- 문제해결: 3/5
...

[최종 추천]
Strong Hire - ...

위 형식을 최대한 지켜서 작성해주세요.
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

        # 간단 파싱: 각 섹션별로 나누기
        summary = ""
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendation = ""
        scores: dict[str, float] = {}

        current_section: str | None = None
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("[요약]"):
                current_section = "summary"
                continue
            if line.startswith("[강점]"):
                current_section = "strengths"
                continue
            if line.startswith("[약점]"):
                current_section = "weaknesses"
                continue
            if line.startswith("[점수표]"):
                current_section = "scores"
                continue
            if line.startswith("[최종 추천]"):
                current_section = "recommendation"
                continue

            if current_section == "summary":
                summary += line + "\n"
            elif current_section == "strengths":
                if line.startswith(("-", "•")):
                    strengths.append(line.lstrip("-• ").strip())
            elif current_section == "weaknesses":
                if line.startswith(("-", "•")):
                    weaknesses.append(line.lstrip("-• ").strip())
            elif current_section == "scores":
                # 예: "- 커뮤니케이션: 4/5"
                if line.startswith(("-", "•")) and ":" in line:
                    try:
                        left, right = line.lstrip("-• ").split(":", 1)
                        label = left.strip()
                        score_part = right.strip().split("/")[0].strip()
                        score_value = float(score_part)
                        scores[label] = score_value
                    except Exception:
                        continue
            elif current_section == "recommendation":
                recommendation += line + " "

        evaluation: EvaluationResult = EvaluationResult(
            summary=summary.strip() or content,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendation=recommendation.strip(),
            scores=scores,
            raw_text=content,
        )

        state["evaluation"] = evaluation
        state["status"] = "DONE"
        state["prev_agent"] = self.role

        return state
