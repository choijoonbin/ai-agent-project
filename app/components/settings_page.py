# app/components/settings_page.py

import os
import streamlit as st


def render_settings_page():
    """
    설정(Settings) 페이지 Stub.
    간단한 버전/환경 정보 및 헬스체크 섹션을 두고,
    필요 시 추가 설정들을 이곳에 모을 수 있습니다.
    """

    st.markdown("## ⚙️ 설정 (Settings)")

    st.markdown("### 🔎 시스템 정보")

    col1, col2 = st.columns(2)
    with col1:
        st.write("📦 App Version", "v0.1.0 (UI 리뉴얼 작업 중)")
        st.write("🌐 API Base URL", os.getenv("API_BASE_URL", "http://localhost:8000/api/v1"))
    with col2:
        st.write("🐍 Python", f"{os.sys.version.split()[0]}")
        st.write("🧱 Framework", "Streamlit")

    st.markdown("---")

    st.info(
        """
        이 화면은 추후 다음과 같은 항목을 포함하도록 확장할 수 있습니다.
        - 백엔드 API 헬스체크 결과
        - LangGraph / Langfuse 상태 표시
        - 모델 버전 및 사용량 모니터링
        - 관리자 전용 설정 (예: RAG 인덱스 재빌드 트리거 등)
        """
    )
