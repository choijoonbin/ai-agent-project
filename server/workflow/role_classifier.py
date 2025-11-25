from __future__ import annotations

from typing import List

from utils.config import get_llm

ROLE_KEYWORDS = {
    "frontend": [
        "frontend",
        "front-end",
        "react",
        "vue",
        "next.js",
        "typescript",
        "ui/ux",
        "api 연동",
        "api 호출",
        "rest api 연동",
        "프론트엔드",
    ],
    "backend": [
        "backend",
        "back-end",
        "spring",
        "django",
        "node.js",
        "backend api",
        "api 서버",
        "rest api 서버",
        "database 설계",
        "db 설계",
    ],
    "product_manager": [
        "product manager",
        "product management",
        "프로덕트 매니저",
        "프로젝트 매니저",
        "pm",
        "prd",
        "roadmap",
        "go-to-market",
        "제품 전략",
        "제품 로드맵",
        "사용자 스토리",
    ],
    "qa": [
        "qa",
        "quality assurance",
        "tester",
        "test automation",
        "selenium",
        "playwright",
    ],
    "data": [
        "data scientist",
        "data engineer",
        "analytics",
        "etl",
        "warehouse",
    ],
    "ml_ai": [
        "machine learning",
        "ml ",
        "ai ",
        "딥러닝",
        "lstm",
        "gpt",
    ],
    "devops": [
        "devops",
        "sre",
        "infrastructure",
        "kubernetes",
        "docker",
    ],
    "design": [
        "designer",
        "design system",
        "visual",
        "ux",
        "ui",
    ],
}


def _heuristic_match(text: str, available_roles: List[str]) -> str | None:
    """
    점수 기반 키워드 매칭: 각 role에 대해 매칭된 키워드 수를 세고,
    가장 많이 매칭된 role을 반환합니다.
    동점인 경우 더 구체적인 키워드(role 이름 자체)가 매칭된 것을 우선합니다.
    """
    lowered = text.lower()
    role_scores: dict[str, int] = {}
    
    for role in available_roles:
        keywords = ROLE_KEYWORDS.get(role, []) + [role.lower()]
        score = 0
        for keyword in keywords:
            if keyword in lowered:
                # role 이름 자체가 매칭되면 더 높은 가중치
                if keyword == role.lower():
                    score += 3
                else:
                    score += 1
        if score > 0:
            role_scores[role] = score
    
    if not role_scores:
        return None
    
    # 가장 높은 점수의 role 반환 (동점이면 첫 번째)
    best_role = max(role_scores.items(), key=lambda x: x[1])[0]
    return best_role


def classify_job_role(
    job_title: str,
    jd_text: str,
    resume_text: str,
    available_roles: List[str],
    default_role: str = "general",
) -> str:
    """
    채용공고(JD) 기준으로 직군(role)을 추정합니다.
    채용공고가 모집하는 역할을 기준으로 평가해야 하므로, JD를 우선적으로 사용합니다.
    
    분류 우선순위:
    1) JD 텍스트 기반 키워드 매칭 (가장 우선)
    2) Job Title 기반 키워드 매칭
    3) JD + Job Title 기반 키워드 매칭
    4) LLM을 통한 JD 기반 분류
    5) 기본값 반환
    
    Note: 이력서(resume_text)는 분류에 사용하지 않습니다.
          채용공고가 모집하는 역할을 기준으로 평가해야 하기 때문입니다.
    """
    # 1) JD 텍스트만으로 분류 시도 (최우선)
    role = _heuristic_match(jd_text, available_roles)
    if role:
        return role
    
    # 2) Job Title만으로 분류 시도
    role = _heuristic_match(job_title, available_roles)
    if role:
        return role
    
    # 3) JD + Job Title 조합으로 분류 시도
    jd_combined = f"{job_title}\n{jd_text}"
    role = _heuristic_match(jd_combined, available_roles)
    if role:
        return role

    # 4) LLM 기반 분류 (JD만 사용, 이력서는 제외)
    try:
        llm = get_llm(use_mini=True, streaming=False)
        roles_str = ", ".join(available_roles)
        prompt = (
            "아래 채용공고(JD)를 보고 모집하는 직군을 선택하세요.\n"
            "중요: 채용공고가 모집하는 역할을 기준으로 판단하세요. 지원자의 이력서는 고려하지 마세요.\n"
            f"가능한 직군 목록: {roles_str}\n"
            "응답 형식은 JSON으로 {\"role\": \"직군\"} 만 출력하세요.\n\n"
            f"[Job Title]\n{job_title}\n\n"
            f"[JD]\n{jd_text[:2000]}\n"
        )
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        # 단순 파싱
        for role_name in available_roles:
            if role_name in content:
                return role_name
    except Exception:
        pass

    return default_role if default_role in available_roles else (available_roles[0] if available_roles else "general")

