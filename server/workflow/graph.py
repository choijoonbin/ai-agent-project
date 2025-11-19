# server/workflow/graph.py

from __future__ import annotations

from langgraph.graph import StateGraph, END

from workflow.state import InterviewState, AgentType, create_initial_state
from workflow.agents.jd_agent import JDAnalyzerAgent
from workflow.agents.resume_agent import ResumeAnalyzerAgent
from workflow.agents.interview_agent import InterviewerAgent
from workflow.agents.judge_agent import JudgeAgent


def create_interview_graph(
    enable_rag: bool = True,
    session_id: str | None = None,
    use_mini: bool = True,
) -> StateGraph:
    """
    면접 플로우를 정의하는 LangGraph 그래프를 생성합니다.

    흐름:
        JD_ANALYZER_AGENT
            ↓
        RESUME_ANALYZER_AGENT
            ↓
        INTERVIEWER_AGENT
            ↓
        JUDGE_AGENT
            ↓
           END
    """

    workflow = StateGraph(InterviewState)

    # 에이전트 인스턴스 생성
    jd_agent = JDAnalyzerAgent(use_rag=enable_rag, k=3, use_mini=use_mini, session_id=session_id)
    resume_agent = ResumeAnalyzerAgent(use_rag=enable_rag, k=3, use_mini=use_mini, session_id=session_id)
    interviewer_agent = InterviewerAgent(use_rag=enable_rag, k=3, use_mini=use_mini, session_id=session_id)
    judge_agent = JudgeAgent(use_rag=enable_rag, k=3, use_mini=use_mini, session_id=session_id)

    # 노드 등록
    workflow.add_node(AgentType.JD_ANALYZER, jd_agent.run)
    workflow.add_node(AgentType.RESUME_ANALYZER, resume_agent.run)
    workflow.add_node(AgentType.INTERVIEWER, interviewer_agent.run)
    workflow.add_node(AgentType.JUDGE, judge_agent.run)

    # 엣지 연결
    workflow.add_edge(AgentType.JD_ANALYZER, AgentType.RESUME_ANALYZER)
    workflow.add_edge(AgentType.RESUME_ANALYZER, AgentType.INTERVIEWER)
    workflow.add_edge(AgentType.INTERVIEWER, AgentType.JUDGE)
    workflow.add_edge(AgentType.JUDGE, END)

    # 시작 노드
    workflow.set_entry_point(AgentType.JD_ANALYZER)

    # 컴파일된 그래프 반환
    return workflow.compile()
