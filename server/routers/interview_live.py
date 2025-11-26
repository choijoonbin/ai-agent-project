# server/routers/interview_live.py

"""
실시간 AI 면접을 위한 API 엔드포인트.
기존 workflow.py의 일괄 실행 방식과 달리, 
질문 단위로 상태를 유지하고 점진적으로 진행합니다.
"""

from __future__ import annotations

import json
import uuid
import base64
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from workflow.state import InterviewState, create_initial_state, QATurn
from workflow.graph import create_interview_graph
from workflow.agents.interview_agent import InterviewerAgent
from workflow.agents.judge_agent import JudgeAgent
from workflow.role_classifier import classify_job_role
from retrieval.loader import get_available_roles
from utils.config import get_langfuse_handler
from utils.openai_audio import synthesize_speech
from db.database import get_db
from db.models import Interview as InterviewModel, Application as ApplicationModel

router = APIRouter(
    prefix="/api/v1/interview-live",
    tags=["interview-live"],
)

# 면접 세션을 메모리에 저장 (실제 프로덕션에서는 Redis 등 사용)
_active_sessions: Dict[str, InterviewState] = {}


# ========== Request/Response Models ========== #

class StartInterviewRequest(BaseModel):
    """면접 시작 요청"""
    application_id: int
    candidate_name: str
    job_title: str
    jd_text: str
    resume_text: str
    total_questions: int = 5
    enable_rag: bool = True


class StartInterviewResponse(BaseModel):
    """면접 시작 응답"""
    session_id: str
    first_question: str
    question_category: str
    current_question_num: int
    total_questions: int


class SubmitAnswerRequest(BaseModel):
    """답변 제출 요청"""
    session_id: str
    answer: str


class SubmitAnswerResponse(BaseModel):
    """답변 제출 응답"""
    status: str  # "continue" or "finished"
    next_question: Optional[str] = None
    question_category: Optional[str] = None
    current_question_num: int
    total_questions: int
    evaluation: Optional[Dict[str, Any]] = None  # 면접 종료 시 평가 결과


class EndInterviewRequest(BaseModel):
    """면접 종료 요청"""
    session_id: str


class EndInterviewResponse(BaseModel):
    """면접 종료 응답"""
    status: str = "success"
    interview_id: Optional[int] = None
    message: str = "면접이 성공적으로 종료되었습니다."
    evaluation: Optional[Dict[str, Any]] = None


# ========== API Endpoints ========== #

@router.post("/start", response_model=StartInterviewResponse)
def start_interview(
    request: StartInterviewRequest,
    db: Session = Depends(get_db),
) -> StartInterviewResponse:
    """
    실시간 면접 세션을 시작합니다.
    1. 기존 Interview 레코드 확인 (이미 질문이 생성되어 있음)
    2. 있으면 기존 질문 사용, 없으면 새로 생성
    3. 세션 ID 반환
    """
    # 지원서 확인
    application = db.query(ApplicationModel).filter(
        ApplicationModel.id == request.application_id
    ).first()
    
    if not application:
        raise HTTPException(status_code=404, detail="지원서를 찾을 수 없습니다.")
    
    # 기존 Interview 레코드 확인 (면접 스튜디오에서 생성된 것)
    existing_interview = db.query(InterviewModel).filter(
        InterviewModel.application_id == request.application_id,
        InterviewModel.status == "DONE"  # 에이전트 실행 완료된 것
    ).order_by(InterviewModel.created_at.desc()).first()
    
    # 세션 ID 생성
    session_id = str(uuid.uuid4())
    
    if existing_interview:
        # 기존 면접 레코드에서 질문 불러오기
        print(f"✅ [INFO] 기존 면접 레코드 발견 (ID: {existing_interview.id})")
        
        # state_json에서 전체 상태 파싱
        state_data = json.loads(existing_interview.state_json)
        qa_history = state_data.get("qa_history", [])
        
        if not qa_history or len(qa_history) == 0:
            raise HTTPException(status_code=500, detail="기존 면접 레코드에 질문이 없습니다.")
        
        # 답변을 빈 문자열로 초기화
        for qa in qa_history:
            qa["answer"] = ""
        
        # 초기 상태 생성 (기존 데이터 사용)
        analyzed_state: InterviewState = {
            "job_title": request.job_title,
            "candidate_name": request.candidate_name,
            "jd_text": request.jd_text,
            "resume_text": request.resume_text,
            "job_role": state_data.get("job_role", "general"),
            "jd_summary": state_data.get("jd_summary", ""),
            "jd_requirements": state_data.get("jd_requirements", []),
            "candidate_summary": state_data.get("candidate_summary", ""),
            "candidate_skills": state_data.get("candidate_skills", []),
            "qa_history": qa_history,
            "current_question_index": 0,
            "total_questions": len(qa_history),
            "status": "INTERVIEW",
            "prev_agent": "",
            "evaluation": None,
        }
        
        first_qa = qa_history[0]
        print(f"✅ [INFO] 기존 질문 로드 완료: {len(qa_history)}개")
        
    else:
        # 기존 레코드가 없으면 새로 생성
        print(f"⚠️ [INFO] 기존 면접 레코드 없음. 새로 생성합니다...")
        
        # 직무 분류
        available_roles = get_available_roles() or ["general"]
        detected_role = classify_job_role(
            job_title=request.job_title,
            jd_text=request.jd_text,
            resume_text=request.resume_text,
            available_roles=available_roles,
        )
        
        # 초기 상태 생성
        initial_state: InterviewState = create_initial_state(
            job_title=request.job_title,
            candidate_name=request.candidate_name,
            jd_text=request.jd_text,
            resume_text=request.resume_text,
            total_questions=request.total_questions,
            job_role=detected_role,
        )
        
        print(f"🔄 [INFO] Graph 생성 및 분석 시작...")
        
        # Graph 생성 및 JD/Resume 분석 단계 실행
        graph = create_interview_graph(
            enable_rag=request.enable_rag,
            session_id=session_id,
            use_mini=True,
        )
        
        langfuse_handler = get_langfuse_handler(session_id=session_id)
        config = {
            "callbacks": [langfuse_handler] if langfuse_handler else [],
            "configurable": {"thread_id": session_id},
            "tags": [f"session:{session_id}", "live_interview"],
        }
        
        # JD_ANALYZER와 RESUME_ANALYZER까지만 실행
        initial_state["status"] = "ANALYZING"
        print(f"🔄 [INFO] JD/Resume 분석 중...")
        analyzed_state = graph.invoke(initial_state, config=config)
        print(f"✅ [INFO] JD/Resume 분석 완료")
        
        # Interviewer Agent로 모든 질문 생성
        print(f"🔄 [INFO] InterviewerAgent로 {request.total_questions}개 질문 생성 시작...")
        interviewer = InterviewerAgent(
            use_rag=request.enable_rag,
            session_id=session_id,
            use_mini=True,
        )
        
        # run() 메서드로 모든 질문 생성
        updated_state = interviewer.run(analyzed_state)
        print(f"✅ [INFO] 질문 생성 완료: {len(updated_state.get('qa_history', []))}개")
        
        # 첫 번째 질문 추출
        if not updated_state["qa_history"] or len(updated_state["qa_history"]) == 0:
            raise HTTPException(status_code=500, detail="질문 생성에 실패했습니다.")
        
        first_qa = updated_state["qa_history"][0]
        
        # 생성된 상태 사용 (모든 질문이 이미 qa_history에 있음)
        analyzed_state = updated_state
    
    analyzed_state["status"] = "INTERVIEW"
    analyzed_state["current_question_index"] = 1
    
    # 추가 필드 (프론트엔드 편의를 위해)
    analyzed_state["application_id"] = request.application_id
    
    # 세션 저장
    _active_sessions[session_id] = analyzed_state
    
    print(f"✅ [INFO] 면접 세션 시작: {session_id}, 지원자: {request.candidate_name}")
    
    return StartInterviewResponse(
        session_id=session_id,
        first_question=first_qa["question"],
        question_category=first_qa.get("category", "일반"),
        current_question_num=1,
        total_questions=request.total_questions,
    )


@router.post("/submit-answer", response_model=SubmitAnswerResponse)
def submit_answer(
    request: SubmitAnswerRequest,
    db: Session = Depends(get_db),
) -> SubmitAnswerResponse:
    """
    답변을 제출하고 다음 질문을 받습니다.
    1. 현재 질문에 답변 저장
    2. 다음 질문 생성 또는 면접 종료
    """
    # 세션 확인
    if request.session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="면접 세션을 찾을 수 없습니다.")
    
    state = _active_sessions[request.session_id]
    
    # 현재 질문에 답변 저장
    current_q_num = state.get("current_question_index", 1)
    if state["qa_history"]:
        last_qa = state["qa_history"][-1]
        last_qa["answer"] = request.answer
        print(f"📝 [INFO] 답변 저장: Q{current_q_num} - {request.answer[:50]}...")
    
    # 모든 질문 완료 여부 확인
    if current_q_num >= state["total_questions"]:
        # 면접 종료 - 평가 실행
        judge = JudgeAgent(session_id=request.session_id)
        evaluation = judge.evaluate(state)
        
        state["status"] = "DONE"
        state["evaluation"] = evaluation
        
        print(f"✅ [INFO] 면접 완료: {request.session_id}")
        
        return SubmitAnswerResponse(
            status="finished",
            current_question_num=current_q_num,
            total_questions=state["total_questions"],
            evaluation=evaluation,
        )
    
    # 다음 질문 가져오기 (이미 생성된 질문 목록에서)
    state["current_question_index"] += 1
    new_q_num = state["current_question_index"]
    
    # 다음 질문이 이미 qa_history에 있는지 확인
    if new_q_num <= len(state["qa_history"]):
        # 이미 생성된 질문 사용
        next_qa = state["qa_history"][new_q_num - 1]
    else:
        # qa_history에 없으면 에러 (정상적으로는 발생하지 않아야 함)
        raise HTTPException(
            status_code=500, 
            detail=f"질문 #{new_q_num}을 찾을 수 없습니다. (총 {len(state['qa_history'])}개 질문 생성됨)"
        )
    
    print(f"❓ [INFO] 다음 질문: Q{new_q_num} - {next_qa['question'][:50]}...")
    
    return SubmitAnswerResponse(
        status="continue",
        next_question=next_qa["question"],
        question_category=next_qa.get("category", "일반"),
        current_question_num=new_q_num,
        total_questions=state["total_questions"],
    )


@router.post("/end", response_model=EndInterviewResponse)
def end_interview(
    request: EndInterviewRequest,
    db: Session = Depends(get_db),
) -> EndInterviewResponse:
    """
    면접을 종료하고 결과를 DB에 저장합니다.
    세션이 없는 경우 (서버 재시작 등) 부분 저장을 시도합니다.
    """
    # 세션 확인
    if request.session_id not in _active_sessions:
        # 세션이 없으면 부분 저장 없이 종료만 처리
        return EndInterviewResponse(
            message="면접 세션이 만료되었습니다. 답변 내역이 일부 저장되지 않을 수 있습니다.",
            interview_id=None,
        )
    
    state = _active_sessions[request.session_id]
    
    # InterviewState 필수 필드 보장 (누락 시 기본값 설정)
    if "rag_contexts" not in state:
        state["rag_contexts"] = {}
    if "rag_docs" not in state:
        state["rag_docs"] = {}
    if "web_search_info" not in state:
        state["web_search_info"] = {}
    if "jd_requirements" not in state:
        state["jd_requirements"] = []
    if "candidate_skills" not in state:
        state["candidate_skills"] = []
    if "status" not in state:
        state["status"] = "INTERVIEW"
    if "prev_agent" not in state:
        state["prev_agent"] = ""
    
    # 평가가 아직 안된 경우 실행
    if "evaluation" not in state or not state["evaluation"]:
        print(f"🤖 [INFO] JudgeAgent 평가 시작...")
        judge = JudgeAgent(session_id=request.session_id)
        # JudgeAgent.run()은 state를 반환하므로, 업데이트된 state를 받음
        updated_state = judge.run(state)
        state.update(updated_state)
        evaluation = state.get("evaluation", "평가 결과 없음")
        print(f"✅ [INFO] JudgeAgent 평가 완료")
    else:
        evaluation = state["evaluation"]
    
    # DB에 저장 (Interview 모델은 state_json에 전체 상태를 JSON으로 저장)
    state["status"] = "DONE"  # 최종 상태 업데이트
    
    # 비디오 경로 확인 (업로드된 경우)
    video_path = state.get("video_path")
    
    interview_record = InterviewModel(
        candidate_name=state["candidate_name"],
        job_title=state["job_title"],
        jd_text=state.get("jd_text", ""),
        resume_text=state.get("resume_text", ""),
        total_questions=state.get("total_questions", 5),
        status="DONE",  # 평가 완료 상태
        state_json=json.dumps(state, ensure_ascii=False),  # 전체 state를 JSON으로 저장
        application_id=state.get("application_id"),
        video_path=video_path,  # 녹화 비디오 경로
    )
    
    db.add(interview_record)
    db.commit()
    db.refresh(interview_record)
    
    # 지원서 상태 업데이트 (인터뷰진행 -> 인터뷰완료)
    if state.get("application_id"):
        application = db.query(ApplicationModel).filter(
            ApplicationModel.id == state["application_id"]
        ).first()
        if application:
            application.status = "INTERVIEW_COMPLETED"  # 인터뷰완료 상태
            db.commit()
            print(f"📋 [INFO] 지원서 상태 업데이트: INTERVIEW -> INTERVIEW_COMPLETED (Application ID: {state['application_id']})")
    
    # 세션 정리 (존재하는 경우에만)
    if request.session_id in _active_sessions:
        del _active_sessions[request.session_id]
        print(f"🗑️ [INFO] 세션 정리 완료: {request.session_id}")
    
    print(f"💾 [INFO] 면접 결과 저장 완료: Interview ID={interview_record.id}")
    
    return EndInterviewResponse(
        status="success",
        interview_id=interview_record.id,
        message="면접이 성공적으로 종료되었습니다.",
        evaluation=evaluation,
    )


@router.get("/session/{session_id}")
def get_session_status(session_id: str) -> Dict[str, Any]:
    """
    현재 면접 세션의 상태를 조회합니다.
    """
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="면접 세션을 찾을 수 없습니다.")
    
    state = _active_sessions[session_id]
    
    return {
        "session_id": session_id,
        "status": state["status"],
        "current_question": state.get("current_question_index", 0),
        "total_questions": state["total_questions"],
        "candidate_name": state["candidate_name"],
        "qa_count": len(state["qa_history"]),
    }


@router.post("/tts")
def text_to_speech(request: dict) -> Response:
    """
    텍스트를 음성으로 변환 (TTS)
    
    Request body:
        - text: 변환할 텍스트
    
    Returns:
        audio/mpeg 형식의 오디오 바이트
    """
    text = request.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="텍스트가 비어있습니다.")
    
    try:
        print(f"🔊 [INFO] TTS 요청: {text[:50]}...")
        audio_bytes = synthesize_speech(text)
        print(f"✅ [INFO] TTS 응답 생성 완료: {len(audio_bytes)} bytes")
        
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=tts.mp3"
            }
        )
    except Exception as e:
        print(f"❌ [ERROR] TTS 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"TTS 생성 실패: {str(e)}")


# 비디오 업로드 요청 스키마
class VideoUploadRequest(BaseModel):
    """비디오 업로드 요청"""
    session_id: str
    video_data: str  # Base64 encoded video


@router.post("/upload-video")
def upload_video(
    request: VideoUploadRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    면접 녹화 비디오를 업로드하고 저장합니다.
    
    Args:
        session_id: 면접 세션 ID
        video_data: Base64 인코딩된 비디오 데이터
    
    Returns:
        저장된 비디오 파일 경로
    """
    try:
        # Base64 디코딩
        video_bytes = base64.b64decode(request.video_data)
        
        # 저장 디렉토리 생성
        video_dir = Path("server/data/interview_recordings")
        video_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성 (session_id 기반)
        video_filename = f"{request.session_id}.webm"
        video_path = video_dir / video_filename
        
        # 파일 저장
        with open(video_path, "wb") as f:
            f.write(video_bytes)
        
        print(f"📹 [INFO] 비디오 저장 완료: {video_path} ({len(video_bytes)} bytes)")
        
        return {
            "status": "success",
            "video_path": str(video_path),
            "file_size": len(video_bytes),
        }
    
    except Exception as e:
        print(f"❌ [ERROR] 비디오 업로드 실패: {e}")
        raise HTTPException(status_code=500, detail=f"비디오 업로드 실패: {str(e)}")

