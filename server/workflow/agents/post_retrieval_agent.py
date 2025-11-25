# server/workflow/agents/post_retrieval_agent.py

"""
Post-Retrieval 에이전트
RAG 검색 결과를 후처리하고, 필요시 웹 검색을 통해 추가 정보를 수집합니다.
Agentic RAG 기술을 적용하여 검색 결과의 품질을 평가하고 개선합니다.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging

from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage

from workflow.state import InterviewState
from utils.config import get_llm, get_langfuse_handler
from utils.web_search import search_web

logger = logging.getLogger(__name__)


class PostRetrievalAgent:
    """
    Post-Retrieval 및 Agentic RAG 에이전트
    
    주요 기능:
    1. 검색 결과 재랭킹 및 관련성 평가
    2. 중복 제거
    3. 관련성 낮은 문서 필터링
    4. 추가 검색 필요 여부 판단
    5. 웹 검색을 통한 정보 보완
    6. 검증 및 최종 컨텍스트 생성
    """

    def __init__(
        self,
        use_mini: bool = True,
        session_id: str | None = None,
        relevance_threshold: float = 0.6,
        enable_web_search: bool = True,
        web_search_quality_threshold: float = 0.5,
        max_web_search_results: int = 3,
    ) -> None:
        self.use_mini = use_mini
        self.session_id = session_id
        self.relevance_threshold = relevance_threshold
        self.enable_web_search = enable_web_search
        self.web_search_quality_threshold = web_search_quality_threshold
        self.max_web_search_results = max_web_search_results

    def evaluate_retrieval_quality(
        self,
        docs: List[Document],
        query: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        검색 결과의 품질을 평가합니다.
        
        Returns:
            {
                "quality_score": float,  # 0.0 ~ 1.0
                "needs_web_search": bool,
                "web_search_query": str | None,
                "issues": List[str],  # 품질 문제점
            }
        """
        if not docs:
            return {
                "quality_score": 0.0,
                "needs_web_search": True,
                "web_search_query": query,
                "issues": ["검색 결과가 없습니다."],
            }

        llm = get_llm(use_mini=self.use_mini, streaming=False)
        handler = get_langfuse_handler(session_id=self.session_id)

        # 검색 결과 요약
        docs_summary = "\n".join([
            f"[문서 {i+1}]\n{doc.page_content[:200]}..."
            for i, doc in enumerate(docs[:5])
        ])

        prompt = f"""
다음은 RAG 검색 결과입니다:

[검색 쿼리]
{query}

[검색 결과]
{docs_summary}

[현재 컨텍스트]
{context[:500] if context else "없음"}

위 검색 결과를 평가하고 다음을 판단해주세요:

1) 검색 결과의 관련성 및 품질 점수 (0.0 ~ 1.0)
2) 추가 웹 검색이 필요한지 여부
3) 웹 검색이 필요하다면 검색 쿼리
4) 발견된 문제점

응답 형식:
[품질 점수]
0.75

[웹 검색 필요]
예/아니오

[웹 검색 쿼리]
(필요한 경우에만) 구체적인 검색 쿼리

[문제점]
- 문제점 1
- 문제점 2
        """.strip()

        messages = [
            SystemMessage(content="당신은 RAG 검색 결과의 품질을 평가하는 전문가입니다."),
            HumanMessage(content=prompt),
        ]

        try:
            if handler:
                response = llm.invoke(messages, config={"callbacks": [handler]})
            else:
                response = llm.invoke(messages)

            content = response.content

            # 파싱
            quality_score = 0.5  # 기본값
            needs_web_search = False
            web_search_query = None
            issues = []

            current_section = None
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("[품질 점수]"):
                    current_section = "quality"
                    continue
                elif line.startswith("[웹 검색 필요]"):
                    current_section = "web_search"
                    continue
                elif line.startswith("[웹 검색 쿼리]"):
                    current_section = "query"
                    continue
                elif line.startswith("[문제점]"):
                    current_section = "issues"
                    continue

                if current_section == "quality":
                    try:
                        quality_score = float(line)
                    except ValueError:
                        pass
                elif current_section == "web_search":
                    needs_web_search = "예" in line or "yes" in line.lower() or "필요" in line
                elif current_section == "query":
                    if line and not line.startswith("("):
                        web_search_query = line
                elif current_section == "issues":
                    if line.startswith(("-", "•")):
                        issues.append(line.lstrip("-• ").strip())

            # 웹 검색 필요 여부를 품질 점수 기반으로 결정
            # 품질 점수가 임계값보다 낮으면 웹 검색 필요
            actual_needs_web_search = needs_web_search or (quality_score < self.web_search_quality_threshold)
            
            return {
                "quality_score": quality_score,
                "needs_web_search": actual_needs_web_search,
                "web_search_query": web_search_query or query,
                "issues": issues,
            }

        except Exception as e:
            logger.error(f"검색 품질 평가 중 오류: {e}")
            return {
                "quality_score": 0.5,
                "needs_web_search": False,
                "web_search_query": None,
                "issues": [f"평가 중 오류 발생: {str(e)}"],
            }

    def rerank_documents(
        self,
        docs: List[Document],
        query: str,
    ) -> List[Document]:
        """
        문서를 재랭킹합니다.
        - 관련성 점수 기반 정렬
        - 중복 제거
        - 관련성 낮은 문서 필터링
        """
        if not docs:
            return []

        # 간단한 재랭킹: LLM을 사용하여 관련성 평가
        llm = get_llm(use_mini=self.use_mini, streaming=False)
        handler = get_langfuse_handler(session_id=self.session_id)

        # 각 문서의 관련성 평가
        doc_scores: List[tuple[Document, float]] = []

        for doc in docs:
            prompt = f"""
다음 문서가 검색 쿼리와 얼마나 관련이 있는지 0.0 ~ 1.0 점수로 평가해주세요.

[검색 쿼리]
{query}

[문서 내용]
{doc.page_content[:500]}

점수만 숫자로 출력하세요 (예: 0.75)
            """.strip()

            messages = [
                SystemMessage(content="당신은 문서의 관련성을 평가하는 전문가입니다."),
                HumanMessage(content=prompt),
            ]

            try:
                if handler:
                    response = llm.invoke(messages, config={"callbacks": [handler]})
                else:
                    response = llm.invoke(messages)

                score_str = response.content.strip()
                try:
                    score = float(score_str)
                except ValueError:
                    # 숫자 파싱 실패 시 기본값
                    score = 0.5
            except Exception as e:
                logger.warning(f"문서 재랭킹 중 오류: {e}")
                score = 0.5

            doc_scores.append((doc, score))

        # 점수 기준 정렬 (높은 점수 순)
        doc_scores.sort(key=lambda x: x[1], reverse=True)

        # 관련성 임계값 이상만 필터링
        filtered_docs = [doc for doc, score in doc_scores if score >= self.relevance_threshold]

        # 중복 제거 (간단한 방법: 내용 유사도 기반)
        unique_docs = []
        seen_contents = set()
        for doc in filtered_docs:
            # 내용의 해시를 사용하여 중복 체크
            content_hash = hash(doc.page_content[:200])  # 처음 200자만 사용
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_docs.append(doc)

        return unique_docs

    def enhance_with_web_search(
        self,
        query: str,
        existing_docs: List[Document],
        max_results: int = 3,
    ) -> List[Document]:
        """
        웹 검색을 통해 추가 정보를 수집합니다.
        """
        if not self.enable_web_search:
            return []

        web_results = search_web(query, max_results=max_results)
        if not web_results:
            return []

        # 웹 검색 결과를 Document 형식으로 변환
        web_docs = []
        for result in web_results:
            content = f"{result.get('title', '')}\n{result.get('snippet', '')}"
            doc = Document(
                page_content=content,
                metadata={
                    "source": result.get("url", "web_search"),
                    "type": "web_search",
                    "role": "general",  # 웹 검색 결과는 일반적으로 general
                }
            )
            web_docs.append(doc)

        return web_docs

    def process(
        self,
        docs: List[Document],
        query: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Post-Retrieval 처리 파이프라인을 실행합니다.
        
        Returns:
            {
                "final_docs": List[Document],
                "quality_evaluation": Dict,
                "web_search_used": bool,
                "web_search_results": List[Document],
            }
        """
        # 1. 검색 결과 품질 평가
        quality_eval = self.evaluate_retrieval_quality(docs, query, context)

        # 2. 재랭킹 및 필터링
        reranked_docs = self.rerank_documents(docs, query)

        # 3. 웹 검색 필요 여부 판단
        web_search_results = []
        web_search_used = False

        if quality_eval["needs_web_search"] and self.enable_web_search:
            web_search_query = quality_eval.get("web_search_query") or query
            web_search_results = self.enhance_with_web_search(
                web_search_query, 
                reranked_docs,
                max_results=self.max_web_search_results,
            )
            web_search_used = len(web_search_results) > 0

        # 4. 최종 문서 통합 (기존 문서 + 웹 검색 결과)
        final_docs = reranked_docs + web_search_results

        # 5. 최종 재랭킹 (통합된 문서들)
        if len(final_docs) > len(reranked_docs):
            final_docs = self.rerank_documents(final_docs, query)

        return {
            "final_docs": final_docs,
            "quality_evaluation": quality_eval,
            "web_search_used": web_search_used,
            "web_search_results": web_search_results,
        }

