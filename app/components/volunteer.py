# app/components/volunteer.py

from __future__ import annotations

import os
import base64
from pathlib import Path
from typing import Any, Dict, List

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


def _get(url: str, *, timeout: int = 30) -> requests.Response:
    return requests.get(url, timeout=timeout)


def _post_multipart(url: str, data: Dict[str, Any], files: Dict[str, Any], *, timeout: int = 120) -> requests.Response:
    return requests.post(url, data=data, files=files, timeout=timeout)


def _patch(url: str, payload: Dict[str, Any], *, timeout: int = 30) -> requests.Response:
    return requests.patch(url, json=payload, timeout=timeout)


def _fetch_recruitments() -> List[Dict[str, Any]]:
    resp = _get(f"{API_BASE_URL}/recruitments/")
    if resp.status_code != 200:
        st.error(f"채용공고 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def _fetch_recruitment_detail(rec_id: int) -> Dict[str, Any] | None:
    resp = _get(f"{API_BASE_URL}/recruitments/{rec_id}")
    if resp.status_code != 200:
        st.error("채용공고 상세 조회 실패")
        return None
    return resp.json()


def _fetch_my_applications(member_id: int) -> List[Dict[str, Any]]:
    resp = _get(f"{API_BASE_URL}/applications/my/{member_id}")
    if resp.status_code != 200:
        st.error("지원 이력 조회 실패")
        return []
    return resp.json()


def _render_tag_chips(rec: Dict[str, Any]) -> None:
    tags = []
    if rec.get("employment_type"):
        tags.append(rec["employment_type"])
    if rec.get("experience_badge"):
        tags.append(rec["experience_badge"])
    elif rec.get("experience_level"):
        tags.append(rec["experience_level"])
    if rec.get("location_badge"):
        tags.append(rec["location_badge"])
    elif rec.get("location"):
        tags.append(rec["location"])
    kws = rec.get("requirement_keywords") or []
    tags.extend(kws[:3])
    if not tags:
        return
    chips = " ".join(
        [
            f"<span style='display:inline-block;padding:6px 12px;border-radius:999px;"
            f"background:rgba(148,163,184,0.18);color:#0f172a;font-weight:600;font-size:0.8rem;margin-right:6px;'>"
            f"{t}</span>"
            for t in tags
        ]
    )
    st.markdown(chips, unsafe_allow_html=True)


def render_job_detail_page() -> None:
    rec_id = st.session_state.get("job_detail_id")
    member_id = st.session_state.get("member_id")
    apps = _fetch_my_applications(member_id) if member_id else []

    if not rec_id:
        st.warning("선택된 채용공고가 없습니다.")
        return

    rec = _fetch_recruitment_detail(rec_id)
    if not rec:
        st.error("채용공고를 불러오지 못했습니다.")
        return

    position = rec.get("first_line") or rec.get("title")
    st.markdown("### 🧭 채용공고 상세")
    st.markdown(f"#### {position}")
    comp = rec.get("company") or ""
    loc = rec.get("location") or ""
    st.caption(f"{comp}{' / ' + loc if loc else ''}")
    _render_tag_chips(rec)

    st.markdown("---")

    left, right = st.columns([1.6, 1.0], gap="large")

    with left:
        st.markdown("## 채용공고")
        raw_text = rec.get("raw_text") or ""
        file_path = rec.get("file_path")
        file_suffix = Path(file_path).suffix.lower() if file_path else ""

        with st.container(border=True):
            if file_path and file_suffix == ".pdf" and Path(file_path).exists():
                try:
                    data = Path(file_path).read_bytes()
                    b64 = base64.b64encode(data).decode("utf-8")
                    pdf_display = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="700px" style="border:none;border-radius:12px;"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                except Exception as e:
                    st.warning(f"PDF 로드에 실패했습니다: {e}")
                    st.markdown(raw_text or "원문을 불러올 수 없습니다.")
            elif raw_text:
                st.markdown(
                    """
                    <div style="
                        max-height: 700px;
                        overflow-y: auto;
                        padding: 14px;
                        background: rgba(248,250,252,0.95);
                        border-radius: 12px;
                        border: 1px solid rgba(148,163,184,0.35);
                        color: #0f172a;
                        white-space: pre-wrap;
                        font-size: 0.95rem;
                        line-height: 1.5;
                    ">
                """,
                    unsafe_allow_html=True,
                )
                st.markdown(raw_text)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("원문을 불러올 수 없습니다. 파일을 확인해주세요.")

    with right:
        st.markdown("### 모집 요약")
        with st.container(border=True):
            st.markdown(f"**지원 기간**: {rec.get('deadline') or '미정'}")
            st.markdown(f"**회사**: {rec.get('company') or '미정'}")
            st.markdown(f"**직무**: {rec.get('role_category') or rec.get('experience_level') or '미정'}")
            st.markdown(f"**구분**: {rec.get('experience_level') or '미정'}")
            st.markdown(f"**유형**: {rec.get('employment_type') or '미정'}")
            st.markdown(f"**지역**: {rec.get('location') or '미정'}")

            active_apps = [a for a in apps if a["status"] in ("SUBMITTED", "UNDER_REVIEW")] if apps else []
            has_active = bool(active_apps)
            btn_label = "지원 진행중" if has_active else "지원하기"

            if st.button(btn_label, use_container_width=True, key=f"detail_apply_{rec_id}"):
                if has_active:
                    # 진행 중 공고 안내
                    rec_list = _fetch_recruitments() or []
                    rec_map = {r["id"]: (r.get("first_line") or r["title"]) for r in rec_list}
                    titles = [rec_map.get(a["recruitment_id"], f"공고 ID {a['recruitment_id']}") for a in active_apps]
                    st.info(f"이미 진행 중인 지원: {', '.join(titles)}")
                else:
                    st.session_state["apply_target_id"] = rec_id
                    st.session_state["detail_apply_open"] = True
                    st.rerun()

        if st.button("⬅ 목록으로", use_container_width=True):
            st.session_state["job_detail_id"] = None
            st.session_state["nav_selected_code"] = "jobs"
            st.rerun()

    # 상세 화면 내 지원 폼
    if st.session_state.get("detail_apply_open") and st.session_state.get("apply_target_id") == rec_id:
        st.markdown("---")
        st.markdown("### 지원서 작성")
        recs = _fetch_recruitments()
        job_list = {r["id"]: r.get("first_line") or r["title"] for r in recs}
        apply_target = st.session_state.get("apply_target_id") or rec_id
        name = st.session_state.get("member_name") or ""
        birth = st.session_state.get("member_birth") or ""
        mbti = st.text_input("MBTI", key="detail_apply_mbti", placeholder="e.g., ENFP")
        first_choice = st.selectbox(
            "1지망",
            options=list(job_list.keys()),
            format_func=lambda x: job_list.get(x, ""),
            index=list(job_list.keys()).index(apply_target) if apply_target in job_list else 0,
            key="detail_apply_first_choice",
        )
        second_choice = st.selectbox(
            "2지망 (선택)",
            options=[None] + list(job_list.keys()),
            format_func=lambda x: "선택 안함" if x is None else job_list.get(x, ""),
            key="detail_apply_second_choice",
        )
        cover = st.text_area("자기소개서", height=200, key="detail_apply_cover")
        resume_file = st.file_uploader("이력서 업로드", type=["pdf", "docx", "txt"], key="detail_apply_resume")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("지원취소", use_container_width=True, key="detail_apply_cancel"):
                st.session_state["detail_apply_open"] = False
                st.session_state["apply_target_id"] = None
                st.rerun()
        with col_b:
            if st.button("최종제출", use_container_width=True, key="detail_apply_submit"):
                if not resume_file:
                    st.error("이력서를 업로드해주세요.")
                elif not first_choice:
                    st.error("1지망을 선택해주세요.")
                elif not name or not birth:
                    st.error("로그인 정보가 유효하지 않습니다. 다시 로그인해주세요.")
                else:
                    files = {"resume": (resume_file.name, resume_file.getvalue(), resume_file.type)}
                    data = {
                        "member_id": member_id,
                        "recruitment_id": apply_target,
                        "first_choice_id": first_choice,
                        "second_choice_id": second_choice or "",
                        "mbti": mbti,
                        "cover_letter": cover,
                    }
                    try:
                        resp = _post_multipart(f"{API_BASE_URL}/applications/submit", data=data, files=files, timeout=180)
                        if resp.status_code != 200:
                            raise RuntimeError(resp.text)
                        st.success("지원이 제출되었습니다!")
                        st.session_state["detail_apply_open"] = False
                        st.session_state["apply_target_id"] = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"지원 제출 실패: {e}")


def render_jobs_page() -> None:
    st.title("📄 채용공고")
    member_id = st.session_state.get("member_id")

    st.markdown(
        """
        <style>
        .jobs-filter {
            position: sticky;
            top: 72px;
            align-self: flex-start;
            padding: 10px;
            border: 1px solid rgba(148,163,184,0.35);
            border-radius: 12px;
            background: rgba(15,23,42,0.92);
            z-index: 10;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    apps = _fetch_my_applications(member_id) if member_id else []
    active_app = next((a for a in apps if a["status"] in ("IN_PROGRESS", "SUBMITTED")), None)

    recs = _fetch_recruitments()
    if not recs:
        return

    cols = st.columns([1.2, 2.8])
    with cols[0]:
        # st.markdown("<div class='jobs-filter'>", unsafe_allow_html=True)
        st.markdown("#### 필터")
        q = st.text_input("키워드 검색", key="jobs_keyword")
        experience = st.multiselect("구분", options=["신입", "경력", "무관"], default=[])
        emp_type = st.multiselect("유형", options=["정규", "계약", "아르바이트", "기타"], default=[])
        location = st.text_input("지역", key="jobs_location")
        st.markdown("</div>", unsafe_allow_html=True)

    filtered = []
    for r in recs:
        if st.session_state.get("jobs_keyword"):
            if st.session_state["jobs_keyword"].lower() not in r["title"].lower():
                continue
        if experience and r.get("experience_level") not in experience:
            continue
        if emp_type and r.get("employment_type") not in emp_type:
            continue
        if location and location not in (r.get("location") or ""):
            continue
        filtered.append(r)

    with cols[1]:
        st.markdown("#### 채용공고 목록")
        for rec in filtered:
            position = rec.get("first_line") or rec.get("title")
            with st.container(border=True):
                st.markdown(
                    f"<div style='font-size:0.9rem;color:#64748b;font-weight:600;'>채용 포지션</div>"
                    f"<div style='font-size:1.25rem;font-weight:700;margin-top:2px;'>{position}</div>",
                    unsafe_allow_html=True,
                )
                loc = rec.get("location") or ""
                st.caption(f"{rec.get('company') or ''}{' | ' + loc if loc else ''}")
                _render_tag_chips(rec)
                subcol1, subcol2 = st.columns([3, 1])
                with subcol1:
                    st.caption(f"상태: {rec.get('status')}")
                with subcol2:
                    if st.button(
                        "상세보기",
                        key=f"rec_{rec['id']}",
                        use_container_width=True,
                    ):
                        st.session_state["job_detail_id"] = rec["id"]
                        st.session_state["nav_selected_code"] = "job_detail"
                        st.rerun()

    # 지원 폼
    if st.session_state.get("apply_page_open"):
        with st.container(border=True):
            st.markdown("### 지원서 작성")
            job_list = {r["id"]: r["title"] for r in recs}
            apply_target = st.session_state.get("apply_target_id") or recs[0]["id"]
            name = st.session_state.get("member_name") or ""
            birth = st.session_state.get("member_birth") or ""
            mbti = st.text_input("MBTI", key="apply_mbti", placeholder="e.g., ENFP")
            first_choice = st.selectbox(
                "1지망",
                options=list(job_list.keys()),
                format_func=lambda x: job_list.get(x, ""),
                index=list(job_list.keys()).index(apply_target) if apply_target in job_list else 0,
                key="apply_first_choice",
            )
            second_choice = st.selectbox(
                "2지망 (선택)",
                options=[None] + list(job_list.keys()),
                format_func=lambda x: "선택 안함" if x is None else job_list.get(x, ""),
                key="apply_second_choice",
            )
            cover = st.text_area("자기소개서", height=200, key="apply_cover")
            resume_file = st.file_uploader("이력서 업로드", type=["pdf", "docx", "txt"], key="apply_resume")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("지원취소", use_container_width=True, key="apply_cancel"):
                    st.session_state["apply_page_open"] = False
                    st.session_state["apply_target_id"] = None
                    st.rerun()
            with col_b:
                if st.button("최종제출", use_container_width=True, key="apply_submit"):
                    if not resume_file:
                        st.error("이력서를 업로드해주세요.")
                    elif not first_choice:
                        st.error("1지망을 선택해주세요.")
                    elif not name or not birth:
                        st.error("로그인 정보가 유효하지 않습니다. 다시 로그인해주세요.")
                    else:
                        files = {"resume": (resume_file.name, resume_file.getvalue(), resume_file.type)}
                        data = {
                            "member_id": member_id,
                            "recruitment_id": apply_target,
                            "first_choice_id": first_choice,
                            "second_choice_id": second_choice or "",
                            "mbti": mbti,
                            "cover_letter": cover,
                        }
                        try:
                            resp = _post_multipart(f"{API_BASE_URL}/applications/submit", data=data, files=files, timeout=180)
                            if resp.status_code != 200:
                                raise RuntimeError(resp.text)
                            st.success("지원이 제출되었습니다!")
                            st.session_state["apply_page_open"] = False
                            st.session_state["apply_target_id"] = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"지원 제출 실패: {e}")


def render_status_page() -> None:
    st.title("📊 진행 현황")
    member_id = st.session_state.get("member_id")
    if not member_id:
        st.warning("로그인 후 확인 가능합니다.")
        return

    apps = _fetch_my_applications(member_id)
    if not apps:
        st.info("제출된 지원서가 없습니다.")
        return

    recs = _fetch_recruitments()
    rec_map = {r["id"]: r for r in recs}

    status_colors = {
        "SUBMITTED": "#0ea5e9",
        "UNDER_REVIEW": "#6366f1",
        "PASSED": "#10b981",
        "REJECTED": "#ef4444",
        "CANCELLED": "#94a3b8",
    }

    status_labels = {
        "SUBMITTED": "지원완료",
        "UNDER_REVIEW": "담당자 확인중",
        "PASSED": "합격",
        "REJECTED": "불합격",
        "CANCELLED": "지원취소",
    }

    st.markdown("#### 나의 지원 현황")
    for app in apps:
        rec = rec_map.get(app["recruitment_id"])
        title = rec.get("first_line") or rec.get("title") if rec else f"공고 ID {app['recruitment_id']}"
        company = rec.get("company") if rec else ""
        status = app.get("status") or "SUBMITTED"
        color = status_colors.get(status, "#94a3b8")
        label = status_labels.get(status, status)

        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{title}**")
                meta_parts = []
                if company:
                    meta_parts.append(company)
                if rec and rec.get("location"):
                    meta_parts.append(rec["location"])
                if meta_parts:
                    st.caption(" | ".join(meta_parts))

                st.markdown(
                    f"<span style='display:inline-block;padding:6px 12px;border-radius:999px;"
                    f"background:{color};color:white;font-weight:700;font-size:0.85rem;'>"
                    f"{label}</span>",
                    unsafe_allow_html=True,
                )

                st.caption(f"제출 시각: {app.get('submitted_at','-')}")

            with c2:
                if status in ("SUBMITTED", "UNDER_REVIEW"):
                    if st.button("지원취소", key=f"cancel_app_{app['id']}", use_container_width=True):
                        try:
                            resp = _patch(
                                f"{API_BASE_URL}/applications/{app['id']}/status",
                                {"status": "CANCELLED"},
                            )
                            if resp.status_code != 200:
                                raise RuntimeError(resp.text)
                            st.success("지원이 취소되었습니다.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"지원 취소 실패: {e}")
                elif status == "CANCELLED":
                    st.caption("취소됨")
                else:
                    st.caption("종료됨")
