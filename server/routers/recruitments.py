# server/routers/recruitments.py

from __future__ import annotations

import os
import json
import re
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.database import get_db
from db import models, schemas
from utils.doc_loader import SUPPORTED_EXTS, load_document_text, ensure_dir
from utils.config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

router = APIRouter(
    prefix="/api/v1/recruitments",
    tags=["recruitments"],
)

BASE_DIR = Path(__file__).resolve().parents[1]
RECRUITMENT_DIR = ensure_dir(BASE_DIR / "data" / "recruitment")
DEFAULT_UPLOAD_DIR = RECRUITMENT_DIR


def _ensure_columns(db: Session) -> None:
    """
    SQLite에 신규 컬럼이 없을 경우 동적으로 추가 (간단 마이그레이션).
    """
    desired_cols = {
        "job_family": "TEXT",
        "start_date": "TEXT",
        "end_date": "TEXT",
        "raw_text": "TEXT",
        "first_line": "TEXT",
        "keywords": "TEXT",
        "posted_by": "INTEGER",
    }
    cur = db.connection().connection.cursor()
    cur.execute("PRAGMA table_info(recruitments)")
    existing = {row[1] for row in cur.fetchall()}
    for col, coltype in desired_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE recruitments ADD COLUMN {col} {coltype}")
    db.commit()


def _summarize_text(text: str, length: int = 400) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.split())
    return cleaned[:length] + ("..." if len(cleaned) > length else "")


def _extract_info(raw_text: str) -> dict:
    """
    raw_text 기반으로 포지션명(첫 줄), 경력, 위치, 키워드 추출 (LLM+휴리스틱)
    """
    first_line = ""
    experience_badge = None
    location_badge = None
    keywords: List[str] = []

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if lines:
        first_line = lines[0][:120]

    # 경력: "3년", "5년 이상" 등 숫자+년
    m = re.search(r"(\d+)\s*년", raw_text)
    if m:
        experience_badge = f"{m.group(1)}년 이상"
    else:
        experience_badge = "경력 무관"

    # 위치: 주요 도시 키워드 스캔
    cities = ["서울", "판교", "성남", "분당", "수원", "용인", "대전", "대구", "부산", "광주", "세종", "울산", "인천"]
    for city in cities:
        if city in raw_text:
            location_badge = city
            break

    # 키워드: bullet/short lines 우선 3개
    bullet_lines = [ln for ln in lines if ln.startswith(("•", "-", "·", "*"))]
    source_lines = bullet_lines if bullet_lines else lines[1:]
    for ln in source_lines:
        if len(keywords) >= 3:
            break
        kw = ln.lstrip("•-·* ").strip()
        if kw:
            keywords.append(kw[:40])

    # LLM 기반 추출 시도
    def _via_llm(text: str) -> dict | None:
        if not text.strip():
            return None
        llm = get_llm(use_mini=True, streaming=False)
        system = SystemMessage(content="채용공고 텍스트에서 배지 정보를 추출하는 도우미입니다. JSON만 반환하세요.")
        user = HumanMessage(
            content=(
                "채용공고 텍스트가 아래에 있습니다. 다음 JSON 형식만 반환하세요:\n"
                "{\n"
                '  "location_badge": "근무지역(예: 서울, 판교 등). 여러 지역일 경우 핵심 1개",\n'
                '  "experience_badge": "숫자+년 정보가 있으면 예: \'3년 이상\', 없으면 \'경력 무관\'",\n'
                '  "requirement_keywords": ["필수자격 또는 핵심 요구사항 키워드 최대 4개"]\n'
                "}\n"
                "- 정규/계약 단어가 없거나 경력 기재가 없으면 experience_badge에 '경력 무관'을 넣으세요.\n"
                "- requirement_keywords는 4개 초과하지 말고, 짧은 키워드를 넣으세요.\n"
                "- JSON 이외의 텍스트를 절대 포함하지 마세요.\n\n"
                f"[채용공고]\n{text[:2000]}\n"
            )
        )
        try:
            resp = llm.invoke([system, user])
            raw = getattr(resp, "content", "") or ""
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            return {
                "location_badge": data.get("location_badge"),
                "experience_badge": data.get("experience_badge"),
                "requirement_keywords": data.get("requirement_keywords") or [],
            }
        except Exception:
            return None

    llm_info = _via_llm(raw_text)
    if llm_info:
        location_badge = llm_info.get("location_badge") or location_badge
        experience_badge = llm_info.get("experience_badge") or experience_badge or "경력 무관"
        keywords = llm_info.get("requirement_keywords") or keywords

    return {
        "first_line": first_line,
        "experience_badge": experience_badge,
        "location_badge": location_badge,
        "requirement_keywords": keywords[:4],
    }


def _seed_from_files(db: Session) -> None:
    """recruitments 테이블이 비어있으면 /data/recruitment 파일을 읽어 메타 생성."""
    _ensure_columns(db)
    # 파일 기준 메타가 없는 경우만 추가
    existing_paths = {r.file_path for r in db.query(models.Recruitment).all()}

    for file_path in RECRUITMENT_DIR.glob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        if str(file_path) in existing_paths:
            continue

        raw_text = ""
        try:
            raw_text = load_document_text(file_path)
        except Exception:
            raw_text = ""

        title = file_path.stem
        summary = _summarize_text(raw_text, length=500)
        info = _extract_info(raw_text)

        rec = models.Recruitment(
            title=title,
            company="미정",
            location=None,
            employment_type="정규",
            experience_level="무관",
            role_category=None,
            deadline=None,
            status="OPEN",
            summary=summary,
            raw_text=raw_text,
            first_line=info["first_line"],
            keywords=json.dumps(info["requirement_keywords"], ensure_ascii=False),
            file_path=str(file_path),
        )
        db.add(rec)
    db.commit()


@router.get("/", response_model=List[schemas.RecruitmentSchema])
def list_recruitments(db: Session = Depends(get_db)) -> List[schemas.RecruitmentSchema]:
    _seed_from_files(db)
    items: List[models.Recruitment] = (
        db.query(models.Recruitment)
        .filter(models.Recruitment.status != "ARCHIVED")
        .order_by(models.Recruitment.created_at.desc())
        .all()
    )
    return items


@router.get("/{recruitment_id}", response_model=schemas.RecruitmentSchema)
def get_recruitment(
    recruitment_id: int,
    db: Session = Depends(get_db),
) -> schemas.RecruitmentSchema:
    _ensure_columns(db)
    rec = db.query(models.Recruitment).filter(models.Recruitment.id == recruitment_id).first()
    if rec is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Recruitment not found")

    # 상세 조회 시 원문 텍스트를 함께 제공 (길이 제한)
    raw_text = ""
    try:
        path = Path(rec.file_path)
        if path.exists():
            raw_text = load_document_text(path)
            if len(raw_text) > 8000:
                raw_text = raw_text[:8000] + "\n...\n(내용이 길어 일부만 표시합니다)"
    except Exception:
        raw_text = ""

    rec.raw_text = raw_text
    info = _extract_info(raw_text)
    rec.first_line = info["first_line"]
    rec.experience_badge = info["experience_badge"]
    rec.location_badge = info["location_badge"]
    rec.requirement_keywords = info["requirement_keywords"]
    rec.keywords = json.dumps(info["requirement_keywords"], ensure_ascii=False)
    return rec


# ========== Admin: 업로드/목록/상태관리 ========== #


@router.post("/admin/upload", response_model=schemas.RecruitmentSchema)
async def upload_recruitment(
    title: str = Form(...),
    company: str = Form("미정"),
    job_family: str = Form(None),
    role_category: str = Form(None),
    employment_type: str = Form(None),
    experience_level: str = Form(None),
    location: str = Form(None),
    start_date: str = Form(None),
    end_date: str = Form(None),
    status: str = Form("OPEN"),
    posted_by: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> schemas.RecruitmentSchema:
    """
    관리자용 채용공고 업로드.
    - 동일 기간에 동일 제목이면 경고(겹침)
    - 파일은 UUID prefix로 저장
    """
    _ensure_columns(db)

    # 기간 겹침 체크 (동일 제목 기준)
    if start_date and end_date:
        overlap = (
            db.query(models.Recruitment)
            .filter(models.Recruitment.title == title)
            .filter(models.Recruitment.start_date.isnot(None))
            .filter(models.Recruitment.end_date.isnot(None))
            .filter(models.Recruitment.start_date <= end_date)
            .filter(models.Recruitment.end_date >= start_date)
            .first()
        )
        if overlap:
            raise HTTPException(status_code=400, detail="동일 기간에 이미 등록된 채용공고가 있습니다.")

    # 파일 저장
    ext = Path(file.filename).suffix
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = DEFAULT_UPLOAD_DIR / filename
    DEFAULT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    save_path.write_bytes(content)

    raw_text = ""
    try:
        raw_text = load_document_text(save_path)
    except Exception:
        raw_text = ""

    info = _extract_info(raw_text)
    summary = _summarize_text(raw_text, length=500)

    rec = models.Recruitment(
        title=title,
        company=company,
        job_family=job_family,
        role_category=role_category,
        employment_type=employment_type,
        experience_level=experience_level,
        location=location,
        start_date=start_date,
        end_date=end_date,
        status=status,
        posted_by=posted_by,
        raw_text=raw_text,
        summary=summary,
        first_line=info["first_line"],
        keywords=json.dumps(info["requirement_keywords"], ensure_ascii=False),
        file_path=str(save_path),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    
    # keywords를 JSON 문자열에서 리스트로 파싱하여 스키마 생성
    return schemas.RecruitmentSchema(
        id=rec.id,
        title=rec.title,
        company=rec.company,
        location=rec.location,
        employment_type=rec.employment_type,
        experience_level=rec.experience_level,
        role_category=rec.role_category,
        job_family=rec.job_family,
        start_date=rec.start_date,
        end_date=rec.end_date,
        deadline=rec.deadline,
        status=rec.status,
        summary=rec.summary,
        raw_text=rec.raw_text,
        first_line=rec.first_line,
        keywords=json.loads(rec.keywords) if rec.keywords else [],
        file_path=rec.file_path,
        posted_by=rec.posted_by,
        created_at=rec.created_at,
    )


@router.get("/admin/list", response_model=List[schemas.RecruitmentAdminSchema])
def admin_list_recruitments(db: Session = Depends(get_db)) -> List[schemas.RecruitmentAdminSchema]:
    _ensure_columns(db)
    # 지원자 수/최근 지원일 집계
    subq = (
        db.query(
            models.Application.recruitment_id.label("rid"),
            func.count(models.Application.id).label("cnt"),
            func.max(models.Application.submitted_at).label("last"),
        )
        .group_by(models.Application.recruitment_id)
        .subquery()
    )
    rows = (
        db.query(models.Recruitment, subq.c.cnt, subq.c.last)
        .outerjoin(subq, models.Recruitment.id == subq.c.rid)
        .filter(models.Recruitment.status != "ARCHIVED")
        .order_by(models.Recruitment.created_at.desc())
        .all()
    )
    results: List[schemas.RecruitmentAdminSchema] = []
    for rec, cnt, last in rows:
        results.append(
            schemas.RecruitmentAdminSchema(
                id=rec.id,
                title=rec.title,
                company=rec.company,
                location=rec.location,
                employment_type=rec.employment_type,
                experience_level=rec.experience_level,
                role_category=rec.role_category,
                job_family=rec.job_family,
                start_date=rec.start_date,
                end_date=rec.end_date,
                deadline=rec.deadline,
                status=rec.status,
                summary=rec.summary,
                raw_text=rec.raw_text,
                first_line=rec.first_line,
                keywords=json.loads(rec.keywords) if rec.keywords else [],
                file_path=rec.file_path,
                posted_by=rec.posted_by,
                created_at=rec.created_at,
                applicant_count=cnt or 0,
                last_application_at=last,
            )
        )
    return results


@router.patch("/admin/{recruitment_id}/status", response_model=schemas.RecruitmentSchema)
def update_recruitment_status(
    recruitment_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
) -> schemas.RecruitmentSchema:
    _ensure_columns(db)
    rec = db.query(models.Recruitment).filter(models.Recruitment.id == recruitment_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Recruitment not found")
    rec.status = status
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
