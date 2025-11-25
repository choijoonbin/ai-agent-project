# app/components/login.py

from __future__ import annotations

import os
from typing import Any, Dict, List
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


def _post(url: str, payload: dict, timeout: int = 30) -> requests.Response:
    return requests.post(url, json=payload, timeout=timeout)


def _get(url: str, *, timeout: int = 30) -> requests.Response:
    return requests.get(url, timeout=timeout)


def _fetch_normal_members() -> List[Dict[str, Any]]:
    """NORMAL 역할의 멤버 목록을 가져옵니다."""
    try:
        resp = _get(f"{API_BASE_URL}/auth/members/normal")
        if resp.status_code != 200:
            return []
        return resp.json()
    except Exception:
        return []


def render_login_page() -> None:
    # 로그인 화면 진입 시 초기 선택/입력값을 정리
    # 회원 정보가 없는 경우에만 초기화 (로그인 중에는 보호)
    if st.session_state.get("nav_selected_code") == "login" and not st.session_state.get("member_id"):
        # 기본 로그인 모드는 지원자
        if "login_mode" not in st.session_state:
            st.session_state["login_mode"] = "지원자 로그인"
        # 입력값 초기화
        st.session_state.setdefault("login_user_name", "")
        st.session_state.setdefault("login_user_birth", "1990-01-01")  # 테스트용 기본값
        st.session_state.setdefault("login_admin_name", "")
        st.session_state.setdefault("login_selected_member_id", None)
    
    # 이미 로그인된 상태에서 로그인 페이지에 접근한 경우 리다이렉트
    if st.session_state.get("member_id") and st.session_state.get("nav_selected_code") == "login":
        role = st.session_state.get("member_role")
        if role == "ADMIN":
            st.session_state["nav_selected_code"] = "manager"
        else:
            st.session_state["nav_selected_code"] = "jobs"
        st.rerun()

    st.markdown(
        """
        <div style="display:flex;gap:32px;align-items:center;flex-wrap:wrap;">
          <div style="flex:1;min-width:280px;">
            <div style="font-size:28px;font-weight:700;line-height:1.2;margin-bottom:16px;">함께 성장할 동료를 찾습니다.</div>
            <div style="opacity:0.8;">지원자는 간단한 정보로 로그인/가입 후 채용공고를 확인하고 지원할 수 있습니다. 관리자는 기존 면접/Insights 메뉴를 그대로 사용할 수 있습니다.</div>
          </div>
          <div style="flex:1;min-width:320px;">
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("#### Log In")
        mode = st.radio(
            "로그인 유형",
            options=["지원자 로그인", "관리자 로그인"],
            horizontal=True,
            label_visibility="collapsed",
            key="login_mode",
        )

        if mode == "관리자 로그인":
            name = st.text_input("관리자 이름", key="login_admin_name")
            if st.button("로그인", use_container_width=True, key="login_admin_btn"):
                if not name.strip():
                    st.error("관리자 이름을 입력해주세요.")
                else:
                    try:
                        resp = _post(
                            f"{API_BASE_URL}/auth/login",
                            {"role_type": "manager", "name": name.strip()},
                        )
                        if resp.status_code != 200:
                            raise RuntimeError(resp.text)
                        data = resp.json()
                        # 회원 정보를 먼저 설정 (원자적으로 한 번에)
                        # 중요: member_id와 member_role을 먼저 설정하여 사이드바에서 올바른 메뉴가 표시되도록 함
                        st.session_state["member_id"] = data["member_id"]
                        st.session_state["member_role"] = data["role"]
                        st.session_state["member_name"] = data["name"]
                        st.session_state["member_birth"] = data["birth"]
                        # nav_selected_code는 마지막에 설정하여 사이드바에서 초기화되지 않도록
                        # member_id가 설정되어 있으면 사이드바에서 nav_selected_code를 덮어쓰지 않음
                        st.session_state["nav_selected_code"] = "manager"
                        st.success("관리자 로그인 성공")
                        # rerun 전에 모든 상태가 설정되었는지 확인
                        st.rerun()
                    except Exception as e:
                        st.error(f"로그인 실패: {e}")
        else:
            # NORMAL 멤버 목록 가져오기
            members = _fetch_normal_members()
            
            if not members:
                st.warning("등록된 지원자가 없습니다. 신규가입을 먼저 진행해주세요.")
                name = st.text_input("이름", key="login_user_name")
                birth = st.text_input("생년월일 (YYYY-MM-DD)", key="login_user_birth", value="1990-01-01", placeholder="1990-01-01")
            else:
                # 멤버 선택 selectbox
                member_options = {f"{m['name']} ({m['birth']})": m for m in members}
                
                # 현재 선택된 멤버의 인덱스 찾기
                current_index = 0
                if st.session_state.get("login_selected_member_id"):
                    for idx, (key, member) in enumerate(member_options.items()):
                        if member["id"] == st.session_state.get("login_selected_member_id"):
                            current_index = idx
                            break
                
                selected_key = st.selectbox(
                    "지원자 선택",
                    options=list(member_options.keys()),
                    key="login_selected_member",
                    index=current_index,
                )
                
                if selected_key:
                    selected_member = member_options[selected_key]
                    name = selected_member["name"]
                    birth = selected_member["birth"]
                    st.session_state["login_user_name"] = name
                    st.session_state["login_user_birth"] = birth
                    st.session_state["login_selected_member_id"] = selected_member["id"]
                else:
                    name = ""
                    birth = "1990-01-01"

            col_l, col_r = st.columns(2)
            with col_l:
                if st.button("로그인", use_container_width=True, key="login_user_btn"):
                    if not name or not birth:
                        st.error("지원자를 선택해주세요.")
                    else:
                        try:
                            resp = _post(
                                f"{API_BASE_URL}/auth/login",
                                {"role_type": "applicant", "name": name.strip(), "birth": birth.strip()},
                            )
                            if resp.status_code != 200:
                                raise RuntimeError(resp.text)
                            data = resp.json()
                            # 회원 정보를 먼저 설정 (원자적으로 한 번에)
                            # 중요: member_id와 member_role을 먼저 설정하여 사이드바에서 올바른 메뉴가 표시되도록 함
                            st.session_state["member_id"] = data["member_id"]
                            st.session_state["member_role"] = data["role"]
                            st.session_state["member_name"] = data["name"]
                            st.session_state["member_birth"] = data["birth"]
                            # nav_selected_code는 마지막에 설정하여 사이드바에서 초기화되지 않도록
                            # member_id가 설정되어 있으면 사이드바에서 nav_selected_code를 덮어쓰지 않음
                            st.session_state["nav_selected_code"] = "jobs"
                            st.success("로그인 성공")
                            st.rerun()
                        except Exception as e:
                            st.error(f"로그인 실패: {e}")
            with col_r:
                if st.button("신규가입", use_container_width=True, key="signup_open_btn"):
                    st.session_state["signup_modal_open"] = True

    st.markdown("</div></div>", unsafe_allow_html=True)

    # 가입 팝업 (streamlit 1.x 호환: 모달 대신 카드 섹션으로 표시)
    if st.session_state.get("signup_modal_open"):
        st.markdown("---")
        with st.container(border=True):
            st.markdown("### 신규 회원 가입")
            new_name = st.text_input("이름", key="signup_name")
            new_birth = st.text_input("생년월일 (YYYY-MM-DD)", key="signup_birth", placeholder="1990-01-01")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("가입하기", use_container_width=True, key="signup_confirm"):
                    if not new_name.strip() or not new_birth.strip():
                        st.error("이름과 생년월일을 입력해주세요.")
                    else:
                        try:
                            resp = _post(
                                f"{API_BASE_URL}/auth/signup",
                                {"name": new_name.strip(), "birth": new_birth.strip()},
                            )
                            if resp.status_code != 200:
                                raise RuntimeError(resp.text)
                            data = resp.json()
                            st.success("가입 완료! 로그인 후 이용해주세요.")
                            st.session_state["signup_modal_open"] = False
                        except Exception as e:
                            st.error(f"가입 실패: {e}")
            with col2:
                if st.button("닫기", use_container_width=True, key="signup_close"):
                    st.session_state["signup_modal_open"] = False
                    st.rerun()
