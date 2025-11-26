# app/components/candidate_form.py

from __future__ import annotations

import os
import base64
from pathlib import Path
from typing import Any, Dict, List

import requests
import streamlit as st
from docx import Document
from PyPDF2 import PdfReader

from utils.time_utils import format_to_kst

# 과거 면접 렌더링 유틸 (History에서 사용)
from components.studio_back import render_evaluation, render_questions

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# ---------- API helpers ---------- #

def _get(url: str, *, timeout: int = 30) -> requests.Response:
    return requests.get(url, timeout=timeout)


def _post(url: str, payload: Dict[str, Any], *, timeout: int = 120) -> requests.Response:
    return requests.post(url, json=payload, timeout=timeout)


def _patch(url: str, payload: Dict[str, Any], *, timeout: int = 30) -> requests.Response:
    return requests.patch(url, json=payload, timeout=timeout)


def fetch_applications_all() -> List[Dict[str, Any]]:
    resp = _get(f"{API_BASE_URL}/applications/all", timeout=60)
    if resp.status_code != 200:
        st.error(f"지원자 목록 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def fetch_recruitment_detail(rec_id: int) -> Dict[str, Any] | None:
    resp = _get(f"{API_BASE_URL}/recruitments/{rec_id}", timeout=60)
    if resp.status_code != 200:
        st.error(f"채용공고 조회 실패: {resp.status_code}")
        return None
    return resp.json()


# ---------- Resume loader (app-side) ---------- #

def load_document_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".md":
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        reader = PdfReader(str(path))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return "\n\n".join(texts)
    if ext == ".docx":
        doc = Document(str(path))
        lines = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(lines)
    raise ValueError(f"Unsupported file extension: {ext}")


# ---------- UI helpers ---------- #

def _render_stepper(current: int) -> None:
    steps = [(1, "지원자 선택"), (2, "이력서 확인"), (3, "에이전트 실행")]
    st.markdown(
        """
        <style>
        .stepper-container {display:flex;align-items:center;gap:10px;margin-bottom:1rem;}
        .stepper-step {display:flex;flex-direction:column;align-items:center;font-size:0.85rem;min-width:90px;}
        .stepper-circle {width:28px;height:28px;border-radius:999px;display:flex;align-items:center;justify-content:center;
            font-size:0.85rem;font-weight:700;border:2px solid rgba(148,163,184,0.6);background:rgba(15,23,42,0.9);color:#e5e7eb;}
        .stepper-circle-active {background:#f97373;border-color:#fef3c7;color:#111827;}
        .stepper-line {flex:1;height:2px;background:linear-gradient(90deg, rgba(148,163,184,0.5), rgba(55,65,81,0.3));}
        </style>
        """,
        unsafe_allow_html=True,
    )
    html = ['<div class="stepper-container">']
    for i, (num, label) in enumerate(steps):
        active_class = " stepper-circle-active" if num == current else ""
        html.append('<div class="stepper-step">')
        html.append(f'<div class="stepper-circle{active_class}">{num}</div>')
        html.append(f'<div style="margin-top:4px;text-align:center;">{label}</div>')
        html.append("</div>")
        if i < len(steps) - 1:
            html.append('<div class="stepper-line"></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _status_badge(status: str) -> str:
    labels = {
        "SUBMITTED": "지원완료",
        "DOCUMENT_REVIEW": "서류심사",
        "INTERVIEW": "인터뷰진행",
        "INTERVIEW_COMPLETED": "인터뷰완료",
        "PASSED": "합격",
        "REJECTED": "불합격",
        "CANCELLED": "지원취소",
    }
    colors = {
        "SUBMITTED": "#0ea5e9",
        "DOCUMENT_REVIEW": "#6366f1",
        "INTERVIEW": "#f97316",
        "INTERVIEW_COMPLETED": "#8b5cf6",
        "PASSED": "#10b981",
        "REJECTED": "#ef4444",
        "CANCELLED": "#94a3b8",
    }
    label = labels.get(status, status)
    color = colors.get(status, "#94a3b8")
    return (
        f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;"
        f"background:{color};color:white;font-weight:600;font-size:0.75rem;margin-left:12px;vertical-align:middle;'>{label}</span>"
    )


# ---------- Main render ---------- #

def render_studio_page() -> None:
    st.title("🧑‍💼 면접 스튜디오")
    _render_stepper(1)

    # 이력서 뷰어 닫기 후 해당 지원자 카드로 스크롤 이동
    scroll_to_app_id = st.session_state.get("studio_scroll_to_app_id")
    if scroll_to_app_id:
        st.markdown(
            f"""
            <script>
            (function() {{
                function scrollToCard() {{
                    const card = document.getElementById('app-card-{scroll_to_app_id}');
                    if (card) {{
                        card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        // 하이라이트 효과
                        card.style.transition = 'box-shadow 0.3s ease';
                        card.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.5)';
                        setTimeout(function() {{
                            card.style.boxShadow = '';
                        }}, 2000);
                        return true;
                    }}
                    return false;
                }}
                // 즉시 시도
                if (!scrollToCard()) {{
                    // DOM이 준비되지 않았으면 재시도
                    setTimeout(scrollToCard, 200);
                    setTimeout(scrollToCard, 500);
                    setTimeout(scrollToCard, 1000);
                }}
            }})();
            </script>
            """,
            unsafe_allow_html=True,
        )
        # 플래그 제거
        st.session_state["studio_scroll_to_app_id"] = None

    apps = fetch_applications_all()
    selected_resume = st.session_state.get("studio_selected_resume")
    selected_resume_label = st.session_state.get("studio_selected_resume_label")
    last_agent = st.session_state.get("studio_agent_result")

    # 목록 펼침/접힘 상태 관리 (기본값: True)
    list_expanded = st.session_state.get("studio_list_expanded", True)

    # 지원자 리스트를 expander로 감싸기
    with st.expander("📋 지원자 리스트", expanded=list_expanded):
        if not apps:
            st.info("등록된 지원자가 없습니다. 지원자가 제출을 완료하면 이곳에 표시됩니다.")
        else:
            for app in apps:
                st.markdown(f'<div id="app-card-{app["id"]}">', unsafe_allow_html=True)
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{app.get('member_name','-')}** ({app.get('member_birth','-')})")
                        recruitment_title = app.get("recruitment_title") or app.get("recruitment_first_line") or f"공고 ID {app.get('recruitment_id')}"
                        status = app.get("status","SUBMITTED")
                        st.markdown(f"<div style='margin-bottom:4px;'>{recruitment_title}{_status_badge(status)}</div>", unsafe_allow_html=True)
                        submitted_at = format_to_kst(app.get("submitted_at"))
                        st.caption(f"제출 시각: {submitted_at}")
                    with col2:
                        if st.button(
                            "이력서 보기",
                            key=f"resume_{app['id']}",
                            use_container_width=True,
                            disabled=not app.get("resume_path"),
                        ):
                            st.session_state["studio_selected_resume"] = app.get("resume_path")
                            st.session_state["studio_selected_resume_label"] = app.get("member_name") or app["id"]
                            st.session_state["studio_list_expanded"] = False  # 목록 접기
                            st.session_state["studio_scroll_to_viewer"] = True
                            st.rerun()
                        if st.button(
                            "에이전트 실행",
                            key=f"agent_{app['id']}",
                            use_container_width=True,
                            disabled=not app.get("resume_path"),
                        ):
                            rec_detail = fetch_recruitment_detail(app.get("recruitment_id"))
                            if not rec_detail:
                                st.error("채용공고 정보를 불러오지 못했습니다.")
                            else:
                                resume_path = app.get("resume_path")
                                if not resume_path or not Path(resume_path).exists():
                                    st.error("이력서 파일이 존재하지 않습니다.")
                                else:
                                    with st.spinner("면접 에이전트 실행 중..."):
                                        try:
                                            resume_text = load_document_text(Path(resume_path))
                                            jd_text = rec_detail.get("raw_text") or rec_detail.get("summary") or rec_detail.get("title") or ""
                                            payload = {
                                                "job_title": rec_detail.get("title") or rec_detail.get("first_line") or "미정",
                                                "candidate_name": app.get("member_name") or "지원자",
                                                "jd_text": jd_text,
                                                "resume_text": resume_text,
                                                "total_questions": st.session_state.get("cfg_total_questions", 5),
                                                "enable_rag": st.session_state.get("cfg_enable_rag", True),
                                                "use_mini": st.session_state.get("cfg_use_mini", True),
                                                "save_history": True,
                                                "application_id": app["id"],  # Application ID 전달
                                            }
                                            resp = _post(f"{API_BASE_URL}/workflow/interview/run", payload, timeout=300)
                                            if resp.status_code != 200:
                                                raise RuntimeError(resp.text)
                                            data = resp.json()
                                            st.session_state["studio_agent_result"] = data
                                            st.success("면접 에이전트 실행 완료")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"에이전트 실행 실패: {e}")
                st.markdown('</div>', unsafe_allow_html=True)

    # 선택한 이력서 뷰어
    if selected_resume:
        st.markdown('<div id="resume-viewer-anchor"></div>', unsafe_allow_html=True)
        st.markdown("---")
        
        # 닫기 버튼 (뷰어 위에 배치)
        col_title, col_close = st.columns([3, 1])
        with col_title:
            st.markdown(f"### 이력서 뷰어 - {selected_resume_label}")
        with col_close:
            if st.button("✕ 닫기", use_container_width=True, key="close_resume_viewer"):
                # 이력서 뷰어가 열려있던 지원자 카드 ID 찾기
                current_apps = fetch_applications_all()
                for app in current_apps:
                    if app.get("resume_path") == selected_resume:
                        st.session_state["studio_scroll_to_app_id"] = app["id"]
                        break
                st.session_state["studio_selected_resume"] = None
                st.session_state["studio_selected_resume_label"] = None
                st.session_state["studio_list_expanded"] = True  # 목록 펼치기
                st.rerun()
        
        path = Path(selected_resume)
        if path.exists():
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                try:
                    data = path.read_bytes()
                    b64 = base64.b64encode(data).decode("utf-8")
                    iframe = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="700px" style="border:none;border-radius:12px;"></iframe>'
                    st.markdown(iframe, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"PDF 로드 실패: {e}")
            else:
                try:
                    text = load_document_text(path)
                    st.text_area("이력서 내용", value=text, height=500)
                except Exception as e:
                    st.error(f"이력서 로드 실패: {e}")
        else:
            st.warning("이력서 파일을 찾을 수 없습니다.")
        
        # 이력서 뷰어로 스크롤
        if st.session_state.get("studio_scroll_to_viewer", False):
            st.markdown(
                """
                <script>
                (function() {
                    function scrollToViewer() {
                        const anchor = document.getElementById('resume-viewer-anchor');
                        if (anchor) {
                            const elementPosition = anchor.getBoundingClientRect().top;
                            const offsetPosition = elementPosition + window.pageYOffset - 80;
                            window.scrollTo({
                                top: offsetPosition,
                                behavior: 'smooth'
                            });
                            return true;
                        }
                        return false;
                    }
                    if (document.readyState === 'complete') {
                        setTimeout(scrollToViewer, 500);
                        setTimeout(scrollToViewer, 1000);
                        setTimeout(scrollToViewer, 1500);
                    } else {
                        window.addEventListener('load', function() {
                            setTimeout(scrollToViewer, 500);
                            setTimeout(scrollToViewer, 1000);
                            setTimeout(scrollToViewer, 1500);
                        });
                    }
                })();
                </script>
                """,
                unsafe_allow_html=True,
            )
            st.session_state["studio_scroll_to_viewer"] = False

    # 에이전트 실행 결과 표시
    if last_agent:
        st.markdown("---")
        st.markdown("### 에이전트 실행 결과")
        state = last_agent.get("state", {})
        if state.get("evaluation"):
            render_evaluation(state)
        if state.get("qa_history"):
            render_questions(
                state,
                interview_id=last_agent.get("interview_id"),
                session_prefix="studio_result",
                enable_edit=False,
                update_session_state=False,
            )
