# server/utils/web_search.py

"""
웹 검색 유틸리티 모듈
Tavily Search API를 사용한 웹 검색 기능 제공
"""

from typing import List, Dict, Any, Optional
import logging

from utils.config import get_settings

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    웹 검색을 수행하고 결과를 반환합니다.
    
    Tavily Search API를 우선 사용하고, 실패 시 LLM Knowledge Base를 사용합니다.
    
    Args:
        query: 검색 쿼리
        max_results: 최대 결과 수
        
    Returns:
        검색 결과 리스트 [{"title": "...", "snippet": "...", "url": "..."}, ...]
    """
    settings = get_settings()
    priority = settings.WEB_SEARCH_PRIORITY.split(",")
    
    for method in priority:
        method = method.strip()
        try:
            if method == "tavily":
                results = search_with_tavily(query, max_results)
                if results:
                    logger.info(f"Tavily Search API 성공: {query}")
                    return results
            elif method == "llm_knowledge":
                results = search_with_llm_knowledge(query, max_results)
                if results:
                    logger.info(f"LLM Knowledge Base 사용: {query}")
                    return results
        except Exception as e:
            logger.debug(f"웹 검색 방법 '{method}' 실패: {e}")
            continue
    
    logger.warning(f"모든 웹 검색 방법 실패: {query}")
    return []


def search_with_llm_knowledge(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    LLM의 지식을 활용하여 정보를 추출합니다.
    실제 웹 검색은 아니지만, LLM이 알고 있는 최신 정보를 제공합니다.
    """
    try:
        from utils.config import get_llm
        from langchain_core.messages import SystemMessage, HumanMessage
        
        llm = get_llm(use_mini=True, streaming=False)
        
        prompt = f"""
다음 주제에 대한 최신 정보를 제공해주세요. 
가능한 한 구체적이고 정확한 정보를 제공하고, 출처가 있다면 언급해주세요.

[주제]
{query}

응답 형식:
[제목]
...

[내용]
...

[출처]
...
        """.strip()
        
        messages = [
            SystemMessage(content="당신은 최신 정보를 제공하는 전문가입니다."),
            HumanMessage(content=prompt),
        ]
        
        response = llm.invoke(messages)
        content = response.content
        
        # 결과를 표준 형식으로 변환
        return [{
            "title": query,
            "snippet": content[:500],
            "url": "llm_knowledge",
            "source": "LLM Knowledge Base",
        }]
        
    except Exception as e:
        logger.error(f"LLM 기반 정보 추출 중 오류: {e}")
        return []


def search_with_tavily(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Tavily Search API를 사용하여 웹 검색을 수행합니다.
    
    Note: TAVILY_API_KEY가 .env에 설정되어 있어야 합니다.
    """
    try:
        settings = get_settings()
        
        if not settings.TAVILY_API_KEY:
            logger.debug("TAVILY_API_KEY가 설정되지 않았습니다.")
            return []
        
        try:
            from tavily import TavilyClient
        except ImportError:
            logger.error("tavily-python 패키지가 설치되지 않았습니다. 'pip install tavily-python' 실행 필요")
            return []
        
        # Tavily 클라이언트 초기화
        try:
            tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        except Exception as e:
            logger.error(f"Tavily 클라이언트 초기화 실패: {e}")
            return []
        
        # 검색 실행
        try:
            response = tavily_client.search(
                query=query,
                max_results=min(max_results, 20),  # Tavily는 최대 20개
                search_depth="basic",  # "basic" 또는 "advanced"
            )
        except Exception as e:
            logger.error(f"Tavily 검색 실행 실패: {e}")
            logger.debug(f"검색 쿼리: {query}")
            return []
        
        # 결과 변환
        results = []
        response_results = response.get("results", [])
        
        if not response_results:
            logger.debug(f"Tavily 검색 결과 없음: {query}")
            return []
        
        for item in response_results[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),  # Tavily는 "content" 필드 사용
                "url": item.get("url", ""),
            })
        
        logger.info(f"Tavily 검색 성공: {len(results)}개 결과 반환 (쿼리: {query})")
        return results
        
    except ImportError as e:
        logger.error(f"tavily-python 패키지 import 실패: {e}")
        return []
    except Exception as e:
        logger.error(f"Tavily Search API 오류: {e}")
        logger.debug(f"오류 상세: {type(e).__name__}: {str(e)}")
        return []

