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

AGENT_LABELS = {
    "JD_ANALYZER_AGENT": "JD 분석 에이전트",
    "RESUME_ANALYZER_AGENT": "이력서 분석 에이전트",
    "INTERVIEWER_AGENT": "면접관 에이전트",
    "JUDGE_AGENT": "평가 에이전트",
}


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

def _safe_get_state(detail: Dict[str, Any] | None) -> Dict[str, Any]:
    if not detail:
        return {}
    try:
        return json.loads(detail.get("state_json", "{}"))
    except Exception:
        return {}


def _safe_get_evaluation(detail: Dict[str, Any] | None) -> Dict[str, Any]:
    if not detail:
        return {}
    state = _safe_get_state(detail)
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
    규칙 기반 '단기/장기 기여도' 추정.
    
    **단기 기여도 계산 기준:**
    - 즉시 활용 가능한 기술/실무 역량 점수 평균
    - 포함 역량: 기술 역량, 문제해결, 성능 최적화, 품질 관리, 커뮤니케이션, 리더십 등
    - 즉시 프로젝트에 투입되어 기여할 수 있는 역량
    
    **장기 성장성 계산 기준:**
    - 성장 잠재력과 학습 능력을 나타내는 역량 점수 평균
    - 포함 역량: 학습 능력, 적응력, 잠재력, 혁신성, 리더십(장기 관점), 문제해결(복잡한 문제)
    - 회사와 함께 성장하며 장기적으로 기여할 수 있는 역량
    - 단기 기여도와의 차이: 현재 역량 대비 성장 가능성
    
    **계산 방식:**
    1. 단기 기여도: 기술/실무 역량들의 가중 평균 (기술 역량, 문제해결, 성능 최적화 등)
    2. 장기 성장성: 전체 역량 평균에서 단기 기여도와의 차이를 고려하여 계산
       - 전체 역량이 높으면 성장성도 높음
       - 단기 기여도 대비 전체 역량의 균형을 고려
    """
    if not scores:
        return {"short_term": 3.0, "long_term": 3.0}

    # 단기 기여도: 즉시 활용 가능한 기술/실무 역량
    # 기술 역량, 문제해결, 성능 최적화, 품질 관리, 커뮤니케이션, 리더십 등
    short_term_keys = [
        "기술", "백엔드", "프론트엔드", "문제해결", "문제 해결", "Problem", "Tech",
        "성능", "최적화", "품질", "커뮤니케이션", "리더십", "리딩",
        "테스트", "자동화", "아키텍처", "설계", "개발", "코딩"
    ]
    
    # 장기 성장성: 성장 잠재력과 학습 능력
    # 학습 능력, 적응력, 잠재력, 혁신성 등 (명시적으로 있는 경우)
    long_term_keys = [
        "성장", "학습", "잠재력", "Growth", "Potential", "적응", "혁신",
        "개발", "향상", "진화", "변화"
    ]

    def _avg_for(keys: List[str]) -> float | None:
        vals = []
        for name, score in scores.items():
            name_lower = name.lower()
            if any(k.lower() in name_lower for k in keys):
                vals.append(score)
        if not vals:
            return None
        return sum(vals) / len(vals)

    # 단기 기여도: 기술/실무 역량 평균
    short = _avg_for(short_term_keys)
    
    # 전체 평균 계산
    base_avg = sum(scores.values()) / len(scores) if scores else 3.0
    
    # 단기 기여도가 없으면 전체 평균 사용
    if short is None:
        short = base_avg
    
    # 장기 성장성: 명시적 성장 관련 역량이 있으면 그것을 사용, 없으면 전체 역량의 균형 고려
    long_explicit = _avg_for(long_term_keys)
    
    if long_explicit is not None:
        # 명시적 성장 역량이 있으면 그것을 사용
        long = long_explicit
    else:
        # 명시적 성장 역량이 없으면:
        # 1. 전체 역량 평균을 기본값으로 사용
        # 2. 단기 기여도와의 차이를 고려하여 조정
        #    - 단기 기여도가 높으면 장기 성장성도 비슷하게 높게 설정 (균형 잡힌 역량)
        #    - 단기 기여도가 낮으면 장기 성장성도 낮게 설정
        #    - 단, 전체 역량이 다양하면 성장 가능성이 있다고 판단
        long = base_avg
        
        # 역량의 다양성 고려: 역량 종류가 많고 점수가 고르면 성장 가능성 높음
        if len(scores) >= 5:
            # 역량이 다양하면 성장 가능성에 보너스 (최대 0.3점)
            score_variance = sum((v - base_avg) ** 2 for v in scores.values()) / len(scores)
            if score_variance < 1.0:  # 점수가 고르게 분포
                long = min(5.0, base_avg + 0.2)
            else:
                long = base_avg
        else:
            long = base_avg
    
    # 온보딩 로드맵 완수 시 예상 기여도 향상을 장기 성장성에 반영
    # 낮은 점수의 역량이 있으면 온보딩을 통해 개선 가능성이 높다고 판단
    if scores:
        low_scores = [score for score in scores.values() if score < 3.5]
        if low_scores:
            # 낮은 점수 역량이 많을수록 온보딩을 통한 개선 여지가 큼
            improvement_potential = min(0.5, len(low_scores) * 0.15)  # 최대 0.5점 보너스
            long = min(5.0, long + improvement_potential)
        
        # 역량의 균형도 고려: 점수가 고르지 않으면 온보딩을 통해 균형 개선 가능
        score_range = max(scores.values()) - min(scores.values())
        if score_range > 1.5:  # 점수 차이가 크면
            balance_improvement = min(0.3, (score_range - 1.5) * 0.2)  # 최대 0.3점 보너스
            long = min(5.0, long + balance_improvement)

    # 1~5 사이로 클램프
    short = max(1.0, min(5.0, short))
    long = max(1.0, min(5.0, long))
    
    return {"short_term": short, "long_term": long}


def _build_soft_landing_plan(evaluation: Dict[str, Any], scores: Dict[str, float] = None) -> Dict[str, List[str]]:
    """
    evaluation 의 strengths / weaknesses / recommendation 을 활용해
    30/60/90일 온보딩 플랜을 구성하고, 기여도 향상을 위한 목표를 포함.
    (향후 백엔드 AI 인사이트 API 로 대체 가능)
    """
    strengths = evaluation.get("strengths") or []
    weaknesses = evaluation.get("weaknesses") or []
    recommendation = evaluation.get("recommendation") or ""

    plan_30: List[str] = []
    plan_60: List[str] = []
    plan_90: List[str] = []
    
    # 기여도 향상 목표
    contribution_goals_30: List[str] = []
    contribution_goals_60: List[str] = []
    contribution_goals_90: List[str] = []

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

    # 기여도 향상을 위한 목표 추가
    if scores:
        # 낮은 점수의 역량 식별
        low_scores = [(name, score) for name, score in scores.items() if score < 3.5]
        if low_scores:
            low_scores.sort(key=lambda x: x[1])  # 점수 낮은 순으로 정렬
            
            # 30일 목표: 가장 낮은 역량 1-2개 개선
            if len(low_scores) >= 1:
                contribution_goals_30.append("**기여도 향상 목표 (30일):**")
                for name, score in low_scores[:2]:
                    target = min(5.0, score + 0.5)  # 0.5점 향상 목표
                    contribution_goals_30.append(f"- {name}: {score:.1f} → {target:.1f}점 목표")
            
            # 60일 목표: 중간 수준 역량 개선
            mid_scores = [(name, score) for name, score in scores.items() if 3.0 <= score < 4.0]
            if mid_scores:
                contribution_goals_60.append("**기여도 향상 목표 (60일):**")
                for name, score in mid_scores[:2]:
                    target = min(5.0, score + 0.7)  # 0.7점 향상 목표
                    contribution_goals_60.append(f"- {name}: {score:.1f} → {target:.1f}점 목표")
            
            # 90일 목표: 전체 역량 균형 개선
            avg_score = sum(scores.values()) / len(scores)
            if avg_score < 4.0:
                contribution_goals_90.append("**기여도 향상 목표 (90일):**")
                contribution_goals_90.append(f"- 전체 역량 평균: {avg_score:.1f} → {min(5.0, avg_score + 0.8):.1f}점 목표")
                contribution_goals_90.append("- 핵심 역량 2-3개를 4.0점 이상으로 향상")
        else:
            # 모든 역량이 3.5 이상인 경우: 고도화 목표
            contribution_goals_30.append("**기여도 향상 목표 (30일):**")
            contribution_goals_30.append("- 핵심 역량 1개를 4.5점 이상으로 고도화")
            
            contribution_goals_60.append("**기여도 향상 목표 (60일):**")
            contribution_goals_60.append("- 전체 역량을 4.0점 이상으로 유지하며 전문성 강화")
            
            contribution_goals_90.append("**기여도 향상 목표 (90일):**")
            contribution_goals_90.append("- 리더십 및 멘토링 역량 개발로 팀 기여도 확대")

    # 온보딩 플랜과 기여도 향상 목표 통합
    plan_30.extend(contribution_goals_30)
    plan_60.extend(contribution_goals_60)
    plan_90.extend(contribution_goals_90)

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


def _render_rag_sources(state: Dict[str, Any]) -> None:
    job_role = state.get("job_role", "general")
    contexts = state.get("rag_contexts") or {}

    st.markdown(f"**직군 태그**: `{job_role}`")

    if not contexts:
        st.caption("RAG 컨텍스트 기록이 없습니다.")
        return

    for agent_key, context_text in contexts.items():
        label = AGENT_LABELS.get(agent_key, agent_key)
        st.markdown(f"- **{label}**")
        st.code(context_text.strip(), language="text")


# ==============================
# 3) 시각화 유틸 (개선)
# ==============================

def _render_score_chart(scores: Dict[str, float]) -> None:
    if not scores:
        st.info("점수 정보가 없어 시각화를 표시할 수 없습니다.")
        return

    df = pd.DataFrame(
        [{"역량": k, "점수": float(v)} for k, v in scores.items()]
    )

    # Altair 시각화 개선
    chart = (
        alt.Chart(df)
        .mark_bar(color="#4c78a8", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)  # 막대 색상 및 모서리 둥글게
        .encode(
            x=alt.X(
                "역량:N", 
                axis=alt.Axis(labelAngle=-45, title=None, labelLimit=100)  # x축 제목 제거 및 각도 조정
            ),
            y=alt.Y(
                "점수:Q",
                scale=alt.Scale(domain=[0, 5], nice=False),  # 0-5 범위로 고정 (5점 만점 명확화)
                axis=alt.Axis(
                    values=[0, 1, 2, 3, 4, 5],  # y축 눈금 명시적 설정
                    title="점수 (만점: 5점)",
                    grid=True
                )
            ),
            tooltip=["역량", alt.Tooltip("점수", format=".1f")],
        )
        .properties(height=350)  # 차트 높이 증가
    )

    st.altair_chart(chart, use_container_width=True)


def _render_contribution_chart(contrib: Dict[str, float]) -> None:
    df = pd.DataFrame(
        [
            {"구분": "단기 기여도", "점수": contrib.get("short_term", 3.0), "색상": "A"},
            {"구분": "장기 성장성", "점수": contrib.get("long_term", 3.0), "색상": "B"},
        ]
    )

    # Altair 시각화 개선
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("구분:N", axis=alt.Axis(labelAngle=0, title=None)),  # x축 제목 제거
            y=alt.Y(
                "점수:Q",
                scale=alt.Scale(domain=[0, 5], nice=False),  # 0-5 범위로 고정 (5점 만점 명확화)
                axis=alt.Axis(
                    values=[0, 1, 2, 3, 4, 5],  # y축 눈금 명시적 설정
                    title="점수 (만점: 5점)",
                    grid=True
                )
            ),
            color=alt.Color("구분", scale=alt.Scale(domain=["단기 기여도", "장기 성장성"], range=["#e377c2", "#17becf"])),  # 색상 지정
            tooltip=["구분", alt.Tooltip("점수", format=".1f")],
        )
        .properties(height=280)  # 차트 높이 조정
    )

    st.altair_chart(chart, use_container_width=True)

# ==============================
# 4) 메인 렌더 함수 (개선)
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
    state = _safe_get_state(detail)
    evaluation = _safe_get_evaluation(detail)
    scores = _safe_get_scores(evaluation)
    contrib = _estimate_contribution(scores)
    plan = _build_soft_landing_plan(evaluation, scores)  # scores 전달하여 기여도 향상 목표 포함
    risks = _extract_risks(evaluation)

    # 기본 메타 정보
    job_title = detail.get("job_title", "") if detail else ""
    candidate_name = detail.get("candidate_name", "") if detail else ""
    recommendation = evaluation.get("recommendation") or "N/A"
    summary = evaluation.get("summary") or ""

    st.header("👥 후보 정보 & 요약")

    # ------------------------
    # 3) 상단 요약 카드 영역 (개선)
    # ------------------------
    col_a, col_b, col_c = st.columns([1.3, 1.3, 1.2])

    with col_a:
        with st.container(border=True):
            st.subheader("👤 후보 정보", divider='blue')
            st.markdown(f"**후보자**: **{candidate_name or '-'}**")
            st.markdown(f"**포지션**: {job_title or '-'}")
            st.markdown(f"**추천 결과**: `{recommendation}`")

    with col_b:
        with st.container(border=True):
            st.subheader("🚀 기여도 요약", divider='blue')
            # 역량평균, 단기 기여도, 장기 성장성을 같은 라인에 나란히 표시
            baseline = sum(scores.values()) / len(scores) if scores else 3.0
            
            col_avg, col_short, col_long = st.columns(3)
            with col_avg:
                st.metric(
                    label="역량평균", 
                    value=f"{baseline:.1f} / 5"
                )
            with col_short:
                delta_short = contrib['short_term'] - baseline
                delta_text = f"{delta_short:+.1f}점" if delta_short != 0 else "0.0점"
                st.metric(
                    label="단기 기여도", 
                    value=f"{contrib['short_term']:.1f} / 5", 
                    delta=delta_text,
                    delta_color="normal" if delta_short >= 0 else "inverse"
                )
            with col_long:
                delta_long = contrib['long_term'] - baseline
                delta_text = f"{delta_long:+.1f}점" if delta_long != 0 else "0.0점"
                st.metric(
                    label="장기 성장성", 
                    value=f"{contrib['long_term']:.1f} / 5", 
                    delta=delta_text,
                    delta_color="normal" if delta_long >= 0 else "inverse"
                )
            
            # 계산 근거는 st.expander 내부로 이동하여 공간 절약
            if scores:
                short_term_keys = ["기술", "백엔드", "프론트엔드", "문제해결", "문제 해결", "성능", "최적화", "품질", "커뮤니케이션", "리더십"]
                long_term_keys = ["성장", "학습", "잠재력", "적응", "혁신"]
                
                with st.expander("📊 계산 근거", expanded=False):
                    short_matched = [name for name in scores.keys() if any(k.lower() in name.lower() for k in short_term_keys)]
                    long_matched = [name for name in scores.keys() if any(k.lower() in name.lower() for k in long_term_keys)]
                    
                    if short_matched:
                        st.markdown(f"**단기 기여도**: {', '.join(short_matched[:3])}{'...' if len(short_matched) > 3 else ''} 역량의 평균")
                    else:
                        st.markdown(f"**단기 기여도**: 전체 역량 평균 사용")
                    
                    if long_matched:
                        st.markdown(f"**장기 성장성**: {', '.join(long_matched)} 역량의 평균")
                    else:
                        st.markdown(f"**장기 성장성**: 명시적 성장 역량이 없어 전체 역량 평균 및 다양성 고려")
                        st.caption("→ 역량 종류가 다양하고 점수가 고르면 성장 가능성에 보너스 적용")
                    
                    # 온보딩 반영 여부 표시
                    low_scores = [score for score in scores.values() if score < 3.5]
                    if low_scores:
                        improvement_potential = min(0.5, len(low_scores) * 0.15)
                        st.markdown(f"**온보딩 반영**: 낮은 점수 역량 {len(low_scores)}개 개선 여지 → +{improvement_potential:.2f}점 보너스")
                    
                    score_range = max(scores.values()) - min(scores.values()) if scores else 0
                    if score_range > 1.5:
                        balance_improvement = min(0.3, (score_range - 1.5) * 0.2)
                        st.markdown(f"**역량 균형 개선**: 점수 차이 {score_range:.1f}점 → 온보딩을 통한 균형 개선 가능성 +{balance_improvement:.2f}점")
                    
                    st.caption("※ 점수 기반 간단 추정치이며, 내부 평가 기준에 맞게 조정 가능.")


    with col_c:
        with st.container(border=True):
            st.subheader("📝 한 줄 요약", divider='blue')
            if summary:
                # 긴 텍스트는 최대 높이 제한 및 스크롤 적용
                st.markdown(
                    f"""
                    <div style="max-height: 175px; overflow-y: auto; padding: 8px;">
                        {summary}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.caption("Judge 평가 요약이 없어 간단 요약을 표시할 수 없습니다.")

    with st.expander("🔎 직군 & RAG 참고 정보", expanded=False):
        _render_rag_sources(state)

    st.markdown("---")

    # ------------------------
    # 4) 역량 점수 & 기여도 시각화 (개선된 함수 호출)
    # ------------------------
    # 좌측 차트 20% 축소, 우측 차트 20% 확대 (2.4:1.2 = 2:1 비율)
    # 간격을 넓히기 위해 중간에 빈 컬럼 추가
    left, gap, right = st.columns([2, 0.3, 1])

    with left:
        st.subheader("📈 역량별 점수 분포")
        _render_score_chart(scores)

    with gap:
        # 간격을 위한 빈 공간
        st.empty()

    with right:
        st.subheader("🎯 기여도 & 성장성")
        _render_contribution_chart(contrib)

    st.markdown("---")

    # ------------------------
    # 5) Soft-landing 30/60/90 플랜 (카드 형식으로 개선)
    # ------------------------
    st.header("🧭 온보딩 플랜 (30 / 60 / 90일)")

    def render_plan_card(title: str, lines: List[str], icon: str) -> None:
        """온보딩 플랜을 시각적 카드 형태로 렌더링 - 높이 300px 고정"""
        
        st.markdown(f"#### {icon} {title}")
        
        # 내부 컨테이너를 사용하여 구분 - 높이 300px 고정
        # 폰트 사이즈를 후보 정보 & 요약 영역과 통일 (16px 기준)
        content_html = ""
        for line in lines:
            if line.startswith("**기여도 향상 목표"):
                content_html += f"<div style='margin-bottom: 8px; font-size: 16px;'><strong>{line}</strong></div>"
            elif line.startswith("- "):  # 리스트 항목
                content_html += f"<p style='margin: 0; padding-left: 10px; font-size: 16px; margin-bottom: 6px; line-height: 1.5;'>• {line[2:]}</p>"
            else:  # 일반 텍스트
                content_html += f"<p style='margin: 0; margin-bottom: 6px; font-size: 16px; color: #666; line-height: 1.5;'>{line}</p>"
        
        # 카드 전체를 300px 고정 높이로 설정
        st.markdown(
            f"""
            <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1;">
                    {content_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown("")  # 컨테이너 간 간격 확보

    col30, col60, col90 = st.columns(3)

    with col30:
        render_plan_card("첫 30일 (적응 & 학습)", plan["30"], "🚀")

    with col60:
        render_plan_card("60일차까지 (실무 & 기여)", plan["60"], "⚙️")

    with col90:
        render_plan_card("90일 이후 (성장 & 정의)", plan["90"], "🗺️")

    st.markdown("---")

    # ------------------------
    # 6) 리스크 & 케어 포인트 (개선)
    # ------------------------
    st.header("⚠️ 리스크 & 케어 포인트")

    # st.expander를 활용하여 시각적 강조
    with st.expander("🚨 리스크 목록 확인", expanded=True):
        for r in risks:
            st.markdown(f"- **{r}**") # 리스크 항목을 더 강조

    st.caption(
        "※ 위 인사이트는 Judge 평가 요약/강점/약점을 바탕으로 한 규칙 기반 제안입니다. "
        "조직의 평가 기준에 맞게 커스터마이징하거나, 별도의 AI 인사이트 에이전트와 연동할 수 있습니다."
    )