# server/workflow/agents/base_agent.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

from utils.config import get_llm, get_langfuse_handler
from retrieval.vector_store import search_similar_documents
from workflow.state import InterviewState
# PostRetrievalAgent는 지연 로딩 (순환 import 방지)


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
        enable_post_retrieval: bool = True,
        enable_web_search: bool = True,
    ) -> None:
        self.system_prompt = system_prompt
        self.role = role
        self.use_rag = use_rag
        self.k = k
        self.use_mini = use_mini
        self.session_id = session_id
        self.enable_post_retrieval = enable_post_retrieval
        self.enable_web_search = enable_web_search
        
        # Post-Retrieval Agent는 지연 로딩 (순환 import 방지)
        self.post_retrieval_agent = None

    # ================== 공통 유틸 ================== #

    def _build_rag_context(self, state: InterviewState, query: str) -> str:
        """
        RAG를 사용해 유사 문서 검색 후 컨텍스트 텍스트를 만들어 반환.
        Post-Retrieval 및 Agentic RAG를 적용하여 검색 결과를 개선합니다.
        검색 결과는 state["rag_contexts"], state["rag_docs"]에도 저장.
        """
        if not self.use_rag or self.k <= 0:
            return ""

        # 1. Pre-Retrieval: 직군 기반 필터링
        role = state.get("job_role")
        metadata_filter = {"role": role} if role else None
        docs = search_similar_documents(query, k=self.k * 2, metadata_filter=metadata_filter)  # 더 많이 검색 (후처리용)
        if not docs and role and role != "general":
            # fallback to general pool
            docs = search_similar_documents(query, k=self.k * 2, metadata_filter={"role": "general"})
        if not docs:
            return ""

        # 2. Post-Retrieval 및 Agentic RAG 처리
        if self.enable_post_retrieval:
            # 지연 로딩: 순환 import 방지
            if self.post_retrieval_agent is None:
                from workflow.agents.post_retrieval_agent import PostRetrievalAgent
                from utils.config import get_settings
                settings = get_settings()
                
                # 설정에서 성능 튜닝 파라미터 읽기
                relevance_threshold = float(getattr(settings, 'POST_RETRIEVAL_RELEVANCE_THRESHOLD', 0.6))
                web_search_quality_threshold = float(getattr(settings, 'WEB_SEARCH_QUALITY_THRESHOLD', 0.5))
                max_web_search_results = int(getattr(settings, 'MAX_WEB_SEARCH_RESULTS', 3))
                
                self.post_retrieval_agent = PostRetrievalAgent(
                    use_mini=self.use_mini,
                    session_id=self.session_id,
                    enable_web_search=self.enable_web_search,
                    relevance_threshold=relevance_threshold,
                    web_search_quality_threshold=web_search_quality_threshold,
                    max_web_search_results=max_web_search_results,
                )
            
            if self.post_retrieval_agent:
                # 현재 컨텍스트 정보 수집
                existing_context = state.get("rag_contexts", {}).get(self.role, "")
                
                # Post-Retrieval 처리
                post_result = self.post_retrieval_agent.process(
                    docs=docs,
                    query=query,
                    context=existing_context,
                )
                
                # 최종 문서 사용
                final_docs = post_result["final_docs"][:self.k]  # k개만 사용
                
                # 웹 검색 결과가 있으면 추가
                if post_result["web_search_used"]:
                    # 웹 검색 결과를 상세하게 메타데이터에 저장
                    if "web_search_info" not in state:
                        state["web_search_info"] = {}
                    
                    # 웹 검색 결과 상세 정보 추출
                    web_results = post_result["web_search_results"]
                    web_results_detail = []
                    for doc in web_results:
                        if doc.metadata.get("type") == "web_search":
                            content_parts = doc.page_content.split("\n")
                            title = content_parts[0] if content_parts else doc.page_content[:100]
                            snippet = content_parts[1] if len(content_parts) > 1 else doc.page_content[:200]
                            web_results_detail.append({
                                "title": title,
                                "snippet": snippet,
                                "url": doc.metadata.get("source", "unknown"),
                            })
                    
                    # 처리 과정 설명
                    initial_doc_count = len(docs)
                    processing_note = (
                        f"품질 평가 점수 {post_result['quality_evaluation'].get('quality_score', 0):.2f}로 인해 "
                        f"웹 검색이 트리거되었습니다. {len(web_results)}개의 웹 검색 결과를 수집하여 "
                        f"기존 {initial_doc_count}개의 RAG 문서와 통합 후 재랭킹하여 최종 {len(final_docs)}개 문서를 선택했습니다."
                    )
                    
                    state["web_search_info"][self.role] = {
                        "used": True,
                        "query": post_result["quality_evaluation"].get("web_search_query"),
                        "results_count": len(web_results),
                        "results": web_results_detail,
                        "processing": processing_note,
                        "quality_score": post_result["quality_evaluation"].get("quality_score", 0),
                        "issues": post_result["quality_evaluation"].get("issues", []),
                    }
            else:
                # Post-Retrieval Agent 초기화 실패 시 기존 로직 사용
                final_docs = docs[:self.k]
        else:
            # Post-Retrieval 비활성화 시 기존 로직 사용
            final_docs = docs[:self.k]

        if not final_docs:
            return ""

        # 3. 컨텍스트 텍스트 구성
        context_lines: List[str] = []
        for i, doc in enumerate(final_docs):
            source = doc.metadata.get("source", "unknown")
            doc_type = doc.metadata.get("type", "knowledge_base")
            if doc_type == "web_search":
                context_lines.append(f"[웹 검색 결과 {i + 1}] 출처: {source}\n{doc.page_content}")
            else:
                context_lines.append(f"[문서 {i + 1}] 출처: {source}\n{doc.page_content}")

        context_text = "\n\n".join(context_lines)

        # 4. 상태에 저장
        state["rag_contexts"][self.role] = context_text
        state["rag_docs"][self.role] = [d.page_content for d in final_docs]

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
