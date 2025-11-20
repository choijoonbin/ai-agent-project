# app/utils/api_client.py

import os
import requests

import streamlit as st
from dotenv import load_dotenv

# app/.env 로드
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


def call_interview_api(
    job_title: str,
    candidate_name: str,
    jd_text: str,
    resume_text: str,
    total_questions: int = 5,
    enable_rag: bool = True,
    use_mini: bool = True,
    save_history: bool = True,
):
    """면접 워크플로우 최초 실행"""
    url = f"{API_BASE_URL}/workflow/interview/run"

    payload = {
        "job_title": job_title,
        "candidate_name": candidate_name,
        "jd_text": jd_text,
        "resume_text": resume_text,
        "total_questions": total_questions,
        "enable_rag": enable_rag,
        "use_mini": use_mini,
        "save_history": save_history,
    }

    response = requests.post(url, json=payload, timeout=180)
    if response.status_code != 200:
        raise RuntimeError(f"API 오류: {response.status_code} - {response.text}")

    return response.json()


def fetch_interview_list(limit: int = 20):
    """면접 이력 목록 조회"""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        st.error(f"면접 이력 조회 실패: {response.status_code}")
        return []
    return response.json()


def fetch_interview_detail(interview_id: int):
    """특정 면접 이력 상세 조회"""
    url = f"{API_BASE_URL}/interviews/{interview_id}"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        st.error(f"면접 이력 상세 조회 실패: {response.status_code}")
        return None
    return response.json()


def call_rejudge_api(interview_id: int, qa_history: list[dict]):
    """수정된 질문/답변을 기반으로 Judge만 재실행"""
    url = f"{API_BASE_URL}/workflow/interview/rejudge"

    enable_rag = st.session_state.get("cfg_enable_rag", True)
    use_mini = st.session_state.get("cfg_use_mini", True)

    payload = {
        "interview_id": interview_id,
        "qa_history": qa_history,
        "enable_rag": enable_rag,
        "use_mini": use_mini,
    }

    response = requests.post(url, json=payload, timeout=180)
    if response.status_code != 200:
        raise RuntimeError(f"재평가 API 오류: {response.status_code} - {response.text}")

    return response.json()


def call_followup_api(
    interview_id: int,
    question: str,
    answer: str,
    category: str | None = None,
):
    """특정 질문/답변에 대한 후속 질문(재질문) 생성"""
    url = f"{API_BASE_URL}/workflow/interview/followup"

    payload = {
        "interview_id": interview_id,
        "question": question,
        "answer": answer,
        "category": category,
        "use_mini": True,
    }

    response = requests.post(url, json=payload, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(
            f"후속 질문 API 오류: {response.status_code} - {response.text}"
        )

    return response.json()
