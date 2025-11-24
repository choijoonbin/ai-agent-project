# app/components/insights.py

from __future__ import annotations

import os
import json
from typing import Any, Dict, List

import requests
import streamlit as st
import pandas as pd
import altair as alt

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# ==============================
# 1) 공통 API 유틸
# ==============================

def _get(url: str, *, timeout: int = 30) -> requests.Response:
    return requests.get(url, timeout=timeout)


def fetch_interview_list(limit: int = 50) -> List[Dict[str, Any]]:
    """최근 면접 이력 목록 조회 (Insights용 간단 버전)."""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    resp = _get(url, timeout=30)
    if resp.status_code != 200:
        st.error(f"면접 이력 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def fetch_interview_detail(interview_id: int) -> Dict[str, Any] | None:
    """특정 면접 이력 상세 조회."""
    url = f"{API_BASE_URL}/interviews/{interview_id}"
    resp = _get(url, timeout=30)
    if resp.status_code != 200:
        st.error(f"면접 이력 상세 조회 실패: {resp.status_code}")
        return None
    return resp.json()


# ==============================
# 2) 인사이트 계산 헬퍼
# ==============================

def _safe_get_evaluation(detail: Dict[str, Any] | None) -> Dict[str, Any]:
    if not detail:
        return {}
    try:
        state = json.loads(detail.get("state_json", "{}"))
    except Exception:
        return {}
    return state.get("evaluation") or {}


def _safe_get_scores(evaluation: Dict[str, Any]) -> Dict[str, float]:
    scores = evaluation.get("scores") or {}
    safe_scores: Dict[str, float] = {}
    for k, v in scores.items():
        try:
            safe_scores[k] = float(v)
        except Exception:
            continue
    return safe_scores


def _estimate_contribution(scores: Dict[str, float]) -> Dict[str, float]:
    """
    간단한 규칙 기반 '단기/장기 기여도' 추정.
    - 기술 관련 점수 평균 → 단기 기여도
    - 성장/학습/잠재력 관련 키워드 평균 → 장기 기여도
    점수가 없으면 기본 3.0 으로 설정.
    """
    if not scores:
        return {"short_term": 3.0, "long_term": 3.0}

    tech_keys = ["기술", "백엔드", "프론트엔드", "문제 해결", "Problem", "Tech"]
    growth_keys = ["성장", "학습", "잠재력", "Growth", "Potential"]

    def _avg_for(keys: List[str]) -> float | None:
        vals = []
        for name, score in scores.items():
            if any(k in name for k in keys):
                vals.append(score)
        if not vals:
            return None
        return sum(vals) / len(vals)

    short = _avg_for(tech_keys)
    long = _avg_for(growth_keys)

    # 기본값 보정
    base_avg = sum(scores.values()) / len(scores) if scores else 3.0
    if short is None:
        short = base_avg
    if long is None:
        long = base_avg

    # 1~5 사이로 클램프
    short = max(1.0, min(5.0, short))
    long = max(1.0, min(5.0, long))
    return {"short_term": short, "long_term": long}


def _build_soft_landing_plan(evaluation: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    evaluation 의 strengths / weaknesses / recommendation 을 활용해
    30/60/90일 Soft-landing 플랜을 간단히 구성.
    (향후 백엔드 AI 인사이트 API 로 대체 가능)
    """
    strengths = evaluation.get("strengths") or []
    weaknesses = evaluation.get("weaknesses") or []
    recommendation = evaluation.get("recommendation") or ""

    plan_30: List[str] = []
    plan_60: List[str] = []
    plan_90: List[str] = []

    if strengths:
        plan_30.append("팀 온보딩 기간 동안 아래 강점을 바로 활용할 수 있도록 초기 과제를 설계하세요:")
        for s in strengths[:3]:
            plan_30.append(f"- {s}")

    if weaknesses:
        plan_30.append("초기 30일 안에 아래 보완 포인트에 대해 1:1 피드백 세션을 진행하세요.")
        for w in weaknesses[:2]:
            plan_30.append(f"- {w}")

    plan_60.append("60일차에는 실무 프로젝트의 핵심 모듈 하나를 단독으로 맡길 수 있도록 목표를 설정합니다.")
    if strengths:
        plan_60.append("강점을 살릴 수 있는 영역(예: 서비스 안정화, 성능 개선, 신규 기능 PoC)을 중심으로 배치하세요.")

    plan_90.append("90일차에는 조직 내에서 역할과 기대치를 명확히 재정의하고, 중장기 성장 로드맵을 합의합니다.")
    if recommendation:
        plan_90.append(f"최종 추천 결과: **{recommendation}** 에 따라 역할/레벨을 조정할 수 있습니다.")

    if not plan_30:
        plan_30.append("기본 온보딩 플랜: 사내 시스템/도메인 학습, 코딩 컨벤션 이해, 소규모 태스크 수행.")
    if not plan_60:
        plan_60.append("중간 온보딩 플랜: 작은 기능을 단독으로 설계/구현하고 코드리뷰를 통해 피드백 순환 구축.")
    if not plan_90:
        plan_90.append("장기 온보딩 플랜: 담당 영역 정의, 기술/업무 목표 수립, 6~12개월 성장 로드맵 수립.")

    return {"30": plan_30, "60": plan_60, "90": plan_90}


def _extract_risks(evaluation: Dict[str, Any]) -> List[str]:
    """Weaknesses 를 기반으로 '리스크 & 케어 포인트' 리스트 생성."""
    weaknesses = evaluation.get("weaknesses") or []
    risks: List[str] = []

    for w in weaknesses:
        risks.append(w)

    if not risks and evaluation.get("summary"):
        risks.append("요약 내용 상 특이 리스크는 뚜렷하지 않으나, 초기 2~4주 동안 업무 적응도와 커뮤니케이션 패턴을 면밀히 관찰하세요.")

    if not risks:
        risks.append("아직 평가 정보가 충분하지 않습니다. 추가 인터뷰(테크/컬쳐핏)를 통해 리스크를 보완 확인하는 것이 좋습니다.")

    return risks


# ==============================
# 3) 시각화 유틸
# ==============================

def _render_score_chart(scores: Dict[str, float]) -> None:
    if not scores:
        st.info("점수 정보가 없어 시각화를 표시할 수 없습니다.")
        return

    df = pd.DataFrame(
        [{"역량": k, "점수": float(v)} for k, v in scores.items()]
    )

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("역량:N", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("점수:Q", scale=alt.Scale(domain=[0, 5])),
            tooltip=["역량", "점수"],
        )
        .properties(height=260)
    )

    st.altair_chart(chart, use_container_width=True)


def _render_contribution_chart(contrib: Dict[str, float]) -> None:
    df = pd.DataFrame(
        [
            {"구분": "단기 기여도", "점수": contrib.get("short_term", 3.0)},
            {"구분": "장기 성장성", "점수": contrib.get("long_term", 3.0)},
        ]
    )

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("구분:N", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("점수:Q", scale=alt.Scale(domain=[0, 5])),
            tooltip=["구분", "점수"],
        )
        .properties(height=220)
    )

    st.altair_chart(chart, use_container_width=True)


# ==============================
# 4) 메인 렌더 함수
# ==============================

def render_insights_page() -> None:
    """사이드바 '인사이트' 메뉴: 후보별 Soft-landing & 기여도 인사이트 대시보드."""

    st.title("📊 후보 인사이트 & 온보딩 플랜")

    # ------------------------
    # 1) 인터뷰 목록 로딩
    # ------------------------
    interviews = fetch_interview_list(limit=50)
    if not interviews:
        st.info("저장된 면접 이력이 없어 인사이트를 표시할 수 없습니다.")
        return

    # 표시용 옵션 구성
    options = []
    default_index = 0

    preselected_id = st.session_state.get("insights_selected_interview_id") \
        or st.session_state.get("last_interview_id")

    for idx, item in enumerate(interviews):
        iid = item["id"]
        title = item.get("job_title", "")
        name = item.get("candidate_name", "")
        created_at = item.get("created_at", "")
        label = f"[{iid}] {title} - {name} ({created_at})"
        options.append((label, iid))
        if preselected_id and iid == preselected_id:
            default_index = idx

    labels = [o[0] for o in options]
    ids = [o[1] for o in options]

    # ------------------------
    # 2) 인터뷰 선택 UI
    # ------------------------
    selected_label = st.selectbox(
        "인사이트를 보고 싶은 면접 이력을 선택하세요.",
        options=labels,
        index=default_index,
    )
    selected_idx = labels.index(selected_label)
    selected_id = ids[selected_idx]

    # 선택 ID를 세션에 저장 (History 에서도 공유)
    st.session_state["insights_selected_interview_id"] = selected_id

    detail = fetch_interview_detail(selected_id)
    evaluation = _safe_get_evaluation(detail)
    scores = _safe_get_scores(evaluation)
    contrib = _estimate_contribution(scores)
    plan = _build_soft_landing_plan(evaluation)
    risks = _extract_risks(evaluation)

    # 기본 메타 정보
    job_title = detail.get("job_title", "") if detail else ""
    candidate_name = detail.get("candidate_name", "") if detail else ""
    recommendation = evaluation.get("recommendation") or "N/A"
    summary = evaluation.get("summary") or ""

    st.markdown("---")

    # ------------------------
    # 3) 상단 요약 카드 영역
    # ------------------------
    col_a, col_b, col_c = st.columns([1.3, 1.3, 1.2])

    with col_a:
        st.markdown("##### 👤 후보 정보")
        st.markdown(f"**후보자**: {candidate_name or '-'}")
        st.markdown(f"**포지션**: {job_title or '-'}")
        st.markdown(f"**추천 결과**: `{recommendation}`")

    with col_b:
        st.markdown("##### 🚀 기여도 요약")
        st.markdown(
            f"- 단기 기여도: **{contrib['short_term']:.1f} / 5**  \n"
            f"- 장기 성장성: **{contrib['long_term']:.1f} / 5**"
        )
        st.caption("※ 점수 기반 간단 추정치입니다. 내부 평가 기준에 맞게 조정 가능.")

    with col_c:
        st.markdown("##### 📝 한 줄 요약")
        if summary:
            st.write(summary)
        else:
            st.caption("Judge 평가 요약이 없어 간단 요약을 표시할 수 없습니다.")

    st.markdown("---")

    # ------------------------
    # 4) 역량 점수 & 기여도 시각화
    # ------------------------
    left, right = st.columns(2)

    with left:
        st.markdown("#### 📈 역량별 점수 분포")
        _render_score_chart(scores)

    with right:
        st.markdown("#### 🎯 기여도 & 성장성")
        _render_contribution_chart(contrib)

    st.markdown("---")

    # ------------------------
    # 5) Soft-landing 30/60/90 플랜
    # ------------------------
    st.markdown("### 🧭 Soft-landing 플랜 (30 / 60 / 90일)")

    col30, col60, col90 = st.columns(3)

    with col30:
        st.markdown("#### 🗓 첫 30일")
        for line in plan["30"]:
            if line.startswith("- "):
                st.markdown(line)
            else:
                st.write(line)

    with col60:
        st.markdown("#### 🗓 60일차까지")
        for line in plan["60"]:
            if line.startswith("- "):
                st.markdown(line)
            else:
                st.write(line)

    with col90:
        st.markdown("#### 🗓 90일 이후")
        for line in plan["90"]:
            if line.startswith("- "):
                st.markdown(line)
            else:
                st.write(line)

    st.markdown("---")

    # ------------------------
    # 6) 리스크 & 케어 포인트
    # ------------------------
    st.markdown("### ⚠️ 리스크 & 케어 포인트")

    for r in risks:
        st.markdown(f"- {r}")

    st.caption(
        "※ 위 인사이트는 Judge 평가 요약/강점/약점을 바탕으로 한 규칙 기반 제안입니다. "
        "조직의 평가 기준에 맞게 커스터마이징하거나, 별도의 AI 인사이트 에이전트와 연동할 수 있습니다."
    )
