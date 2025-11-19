# server/workflow/agents/base_agent.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

from utils.config import get_llm, get_langfuse_handler
from retrieval.vector_store import search_similar_documents
from workflow.state import InterviewState


class BaseAgent(ABC):
    """
    모든 에이전트가 공통으로 사용하는 베이스 클래스.

    - system_prompt: 역할 정의 프롬프트
    - role: 에이전트 식별용 문자열 (AgentType.*)
    - use_rag: RAG 사용 여부
    - k: RAG 검색 시 가져올 문서 수
    - use_mini: 경량 LLM 사용 여부
    """

    def __init__(
        self,
        system_prompt: str,
        role: str,
        use_rag: bool = True,
        k: int = 3,
        use_mini: bool = True,
        session_id: Optional[str] = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.role = role
        self.use_rag = use_rag
        self.k = k
        self.use_mini = use_mini
        self.session_id = session_id

    # ================== 공통 유틸 ================== #

    def _build_rag_context(self, state: InterviewState, query: str) -> str:
        """
        RAG를 사용해 유사 문서 검색 후 컨텍스트 텍스트를 만들어 반환.
        검색 결과는 state["rag_contexts"], state["rag_docs"]에도 저장.
        """
        if not self.use_rag or self.k <= 0:
            return ""

        docs = search_similar_documents(query, k=self.k)
        if not docs:
            return ""

        # 컨텍스트 텍스트 구성
        context_lines: List[str] = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "unknown")
            context_lines.append(f"[문서 {i + 1}] 출처: {source}\n{doc.page_content}")

        context_text = "\n\n".join(context_lines)

        # 상태에 저장
        state["rag_contexts"][self.role] = context_text
        state["rag_docs"][self.role] = [d.page_content for d in docs]

        return context_text

    def _build_messages(self, system_prompt: str, user_prompt: str) -> List[BaseMessage]:
        """
        LLM 호출용 메시지 리스트 생성 (System + Human).
        """
        messages: List[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return messages

    def _call_llm(self, messages: List[BaseMessage]) -> str:
        """
        LLM을 호출하여 문자열 응답을 반환.
        Langfuse 콜백이 설정되어 있다면 함께 전달.
        """
        llm = get_llm(use_mini=self.use_mini, streaming=False)
        handler = get_langfuse_handler(session_id=self.session_id)

        if handler:
            response = llm.invoke(messages, config={"callbacks": [handler]})
        else:
            response = llm.invoke(messages)

        return response.content

    # ================== 추상 메서드 ================== #

    @abstractmethod
    def run(self, state: InterviewState) -> InterviewState:
        """
        각 에이전트가 상태를 읽고, RAG/LLM을 사용해 상태를 갱신하는 핵심 로직.
        반드시 하위 클래스에서 구현해야 합니다.
        """
        raise NotImplementedError
