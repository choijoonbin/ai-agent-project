import streamlit as st


def render_insights_page():
    """인사이트(Insights) 페이지."""

    st.markdown("## 📊 인사이트 & 추천 (Insights)")

    st.warning(
        """
        이 화면은 **후보자별 Soft-landing 플랜, 기여도 예측, 리스크 분석** 등을
        시각적으로 보여주는 인사이트 대시보드로 확장될 예정입니다.

        계획된 기능 예시:
        - 입사 후 30/60/90일 온보딩 플랜 카드
        - 단기 기여도 / 장기 성장 잠재력 지표 (게이지/차트)
        - 인터뷰 답변 기반 리스크 & 케어포인트 목록
        - 면접 이력에서 바로 이 화면으로 넘겨 받아서 특정 후보 인사이트 보기

        먼저 네비게이션 구조와 기본 틀을 잡은 뒤,
        다음 Phase에서 백엔드 Insights 에이전트 및 API와 함께 구현을 진행하겠습니다.
        """
    )
# app/components/insights_page.py

import streamlit as st


def render_insights_page():
    """
    인사이트(Insights) 페이지 Stub.
    Phase 4에서 Soft-landing / 기여도 분석 등을 실제로 구현할 예정입니다.
    """

    st.markdown("## 📊 인사이트 & 추천 (Insights)")

    st.warning(
        """
        이 화면은 **후보자별 Soft-landing 플랜, 기여도 예측, 리스크 분석** 등을
        시각적으로 보여주는 인사이트 대시보드로 확장될 예정입니다.

        계획된 기능 예시:
        - 입사 후 30/60/90일 온보딩 플랜 카드
        - 단기 기여도 / 장기 성장 잠재력 지표 (게이지/차트)
        - 인터뷰 답변 기반 리스크 & 케어포인트 목록
        - 면접 이력에서 바로 이 화면으로 넘겨 받아서 특정 후보 인사이트 보기

        먼저 네비게이션 구조와 기본 틀을 잡은 뒤,
        다음 Phase에서 백엔드 Insights 에이전트 및 API와 함께 구현을 진행하겠습니다.
        """
    )
