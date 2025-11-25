# server/workflow/agents/judge_agent.py

from __future__ import annotations

from typing import List, Any, Dict

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
        
        # 직군 정보 추출 (RAG 컨텍스트 빌드 전에 먼저 추출)
        job_role = state.get("job_role", "general")

        # RAG 검색 쿼리 개선: 문제해결 역량 차이점 및 다른 직군 경험과의 차이점 강조
        # "다른 직군 경험과의 차이점" 섹션을 명시적으로 검색하도록 키워드 추가
        rag_context = self._build_rag_context(
            state,
            query=f"{job_title} {job_role} 평가 기준 다른 직군 경험과의 차이점 평가 시 주의사항 문제해결 리더십 역량 차이점",
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

**중요 평가 원칙:**
1. 지원자의 현재 직군 경험과 목표 직군({job_title})의 요구사항을 명확히 구분하세요.
2. 유사한 역량이라도 직군별로 다른 의미와 요구사항을 가질 수 있습니다:
   - 예: "리더십"이 개발 직군에서는 기술 리딩, 코드 리뷰, 아키텍처 설계를 의미하지만, 
     프로젝트 관리 직군에서는 프로젝트 목표 설정, 일정 관리, 이해관계자 조율을 의미합니다.
   - 예: "문제해결"이 개발 직군에서는 기술적 문제(성능, 버그, 시스템 안정화) 해결을 의미하지만,
     프로젝트 관리 직군에서는 프로젝트 리스크 관리, 일정 지연 대응, 이해관계자 갈등 해결을 의미합니다.
   - ⚠️ 특히 "문제해결" 역량 평가 시 주의 (매우 중요):
     * 개발 직군의 데이터 기반 문제해결은 기술적 문제(성능 최적화, 버그 수정, 시스템 안정화)를 의미합니다.
     * PM의 프로젝트 문제해결은 프로젝트 리스크 관리, 일정 지연 대응, 이해관계자 갈등 해결을 의미합니다.
     * 이 둘은 완전히 다른 영역입니다. 개발 문제해결 경험만으로는 PM의 프로젝트 문제해결 능력을 평가할 수 없습니다.
     * 데이터 기반 의사결정은 PM 역량의 일부이지만, 프로젝트 문제해결의 전부는 아닙니다.
     * 개발 경험의 문제해결 능력이 PM의 프로젝트 문제해결 능력과 직접적으로 매칭되지 않는 경우, 반드시 보수적으로 평가하세요 (예: 2.5~3.0/5.0, 절대 4.0 이상 주지 마세요).
     * 만약 지원자가 개발 직군이고 목표 직군이 PM인 경우, 문제해결 점수는 3.0/5.0을 초과하지 않도록 주의하세요.
3. 지원자의 현재 직군 경험이 목표 직군 역량의 일부 요소에만 해당할 수 있음을 고려하세요.
4. RAG에서 제공된 평가 기준의 각 역량 항목이 목표 직군에 특화된 요구사항임을 명확히 인식하세요.
5. 지원자의 경험이 목표 직군 역량과 직접적으로 매칭되지 않는 경우, 점수를 보수적으로 평가하세요.

위 정보를 바탕으로 다음을 포함하는 평가 리포트를 작성해주세요:

1) 전체 요약 (3~5문장)
2) 지원자의 주요 강점 리스트
3) 지원자의 주요 약점 리스트
4) 역량별 평가 점수 (예: 커뮤니케이션: 4/5, 문제해결: 3/5, 리더십: 2/5 ...)
   ⚠️ 특히 "문제해결" 역량 평가 시 (매우 중요):
   - 개발 직군 지원자의 경우: 기술적 문제해결(성능 최적화, 버그 수정) 경험을 PM의 프로젝트 문제해결(리스크 관리, 일정 지연 대응, 이해관계자 갈등 해결)로 직접 매핑하지 마세요.
   - 데이터 기반 의사결정은 PM 역량의 일부이지만, 프로젝트 문제해결의 전부는 아닙니다.
   - 개발 경험의 문제해결 능력이 PM의 프로젝트 문제해결 능력과 직접적으로 매칭되지 않는 경우, 반드시 보수적으로 평가하세요.
   - ⚠️ 중요: 개발 직군 지원자가 PM 포지션에 지원한 경우, 문제해결 점수는 절대 3.0/5.0을 초과하지 않도록 하세요. 2.5~3.0/5.0 범위로 평가하세요.
5) 직군별 세분화된 역량 점수 (RAG에서 제공된 평가 기준의 배점을 참고하여 각 역량별로 점수와 배점을 명시)
6) 전환 가능성 분석 (지원자의 현재 배경과 목표 포지션 간의 차이, 전환 가능성, 구체적 제안)
7) 최종 추천 (예: Strong Hire / Hire / No Hire) 및 한 줄 코멘트

응답 형식 예시:

[요약]
...

[강점]
- ...

[약점]
- ...

[점수표]
- 커뮤니케이션: 4/5
- 문제해결: 3/5 (주의: 개발 직군의 문제해결과 목표 직군의 문제해결을 구분하여 평가)
- 리더십: 2/5 (주의: 개발 리딩과 목표 직군의 리더십을 구분하여 평가)
...

[세분화된 역량 점수]
- RAG에서 제공된 평가 기준의 각 역량별로 배점을 참고하여 점수를 부여하세요.
- 각 역량 항목은 목표 직군({job_title})에 특화된 요구사항임을 명확히 인식하고 평가하세요.
- 지원자의 현재 직군 경험이 목표 직군 역량과 직접적으로 매칭되는지 신중히 판단하세요.
- 예시:
  - [역량명]: [점수]/[배점] ([비율]%)
  - 각 역량에 대해 지원자의 경험이 해당 역량의 요구사항을 얼마나 충족하는지 평가하세요.
- 다른 직군의 경우 해당 직군의 평가 기준에 맞는 역량 항목으로 작성하세요.

[전환 가능성]
- 지원자의 실제 배경(이력서 요약 참고)과 목표 포지션({job_title}) 간의 차이를 분석하세요.
- 가능성: 높음/보통/낮음 (1~5점 척도로 평가)
- 점수: X.X/5.0
- 현재 배경: [지원자 이력 요약에서 추출한 실제 배경, 예: "Backend 개발자 (7년 경력)", "Frontend 개발자 (3년 경력)" 등]
- 목표 포지션: {job_title}
- 차이점:
  - [현재 배경과 목표 포지션 간의 구체적인 차이점을 나열]
  - [부족한 역량이나 경험을 명시]
- 구체적 제안:
  - [전환을 위한 구체적이고 실행 가능한 제안 사항]
  - [교육, 경험 축적, 역량 강화 방안 등]

[최종 추천]
Hire - 기술적 배경과 문제 해결 능력은 뛰어나지만, PM 역할에 필요한 경험이 부족하여 추가 교육 및 멘토링을 통해 성장할 가능성 있음.

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
        detailed_scores: Dict[str, Dict[str, float]] = {}
        career_transition: Dict[str, Any] = {
            "가능성": "보통",
            "점수": 3.0,
            "현재_배경": "",
            "목표_포지션": job_title,
            "차이점": [],
            "구체적_제안": [],
        }

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
            if line.startswith("[세분화된 역량 점수]"):
                current_section = "detailed_scores"
                continue
            if line.startswith("[전환 가능성]"):
                current_section = "career_transition"
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
            elif current_section == "detailed_scores":
                # 예: "- 프로젝트 계획 및 일정 관리: 22.5/30 (75%)"
                if line.startswith(("-", "•")) and ":" in line:
                    try:
                        left, right = line.lstrip("-• ").split(":", 1)
                        label = left.strip()
                        # "22.5/30 (75%)" 형태 파싱
                        parts = right.strip().split()
                        score_str = parts[0]  # "22.5/30"
                        score_value, max_score = map(float, score_str.split("/"))
                        ratio = score_value / max_score if max_score > 0 else 0.0
                        detailed_scores[label] = {
                            "점수": score_value,
                            "배점": max_score,
                            "비율": ratio,
                        }
                    except Exception:
                        continue
            elif current_section == "career_transition":
                # 전환 가능성 파싱
                if line.startswith("가능성:"):
                    possibility = line.split(":", 1)[1].strip()
                    career_transition["가능성"] = possibility
                elif line.startswith("점수:"):
                    try:
                        score_str = line.split(":", 1)[1].strip().split("/")[0].strip()
                        career_transition["점수"] = float(score_str)
                    except Exception:
                        pass
                elif line.startswith("현재 배경:"):
                    career_transition["현재_배경"] = line.split(":", 1)[1].strip()
                elif line.startswith("목표 포지션:"):
                    career_transition["목표_포지션"] = line.split(":", 1)[1].strip()
                elif line.startswith("차이점:"):
                    current_section = "career_transition_diff"
                elif line.startswith("구체적 제안:"):
                    current_section = "career_transition_suggestions"
                elif line.startswith(("-", "•")):
                    # 차이점 또는 구체적 제안 항목 (섹션 헤더 없이 바로 나올 경우)
                    item = line.lstrip("-• ").strip()
                    # 기본적으로 차이점으로 추가 (나중에 구체적 제안 섹션을 만나면 이동)
                    career_transition["차이점"].append(item)
            elif current_section == "career_transition_diff":
                if line.startswith(("-", "•")):
                    career_transition["차이점"].append(line.lstrip("-• ").strip())
            elif current_section == "career_transition_suggestions":
                if line.startswith(("-", "•")):
                    career_transition["구체적_제안"].append(line.lstrip("-• ").strip())
            elif current_section == "recommendation":
                recommendation += line + " "

        evaluation: EvaluationResult = EvaluationResult(
            summary=summary.strip() or content,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendation=recommendation.strip(),
            scores=scores,
            detailed_scores=detailed_scores,
            career_transition=career_transition,
            raw_text=content,
        )

        state["evaluation"] = evaluation
        state["status"] = "DONE"
        state["prev_agent"] = self.role

        return state
