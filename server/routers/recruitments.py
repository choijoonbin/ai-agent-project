# server/routers/recruitments.py

from __future__ import annotations

import os
from pathlib import Path
from typing import List
import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from db import models, schemas
from utils.doc_loader import SUPPORTED_EXTS, load_document_text, ensure_dir

router = APIRouter(
    prefix="/api/v1/recruitments",
    tags=["recruitments"],
)

BASE_DIR = Path(__file__).resolve().parents[1]
RECRUITMENT_DIR = ensure_dir(BASE_DIR / "data" / "recruitment")


def _summarize_text(text: str, length: int = 400) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.split())
    return cleaned[:length] + ("..." if len(cleaned) > length else "")


def _extract_info(raw_text: str) -> dict:
    """
    raw_text 기반으로 포지션명(첫 줄), 경력, 위치, 키워드 추출
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

    return {
        "first_line": first_line,
        "experience_badge": experience_badge,
        "location_badge": location_badge,
        "requirement_keywords": keywords,
    }


def _seed_from_files(db: Session) -> None:
    """recruitments 테이블이 비어있으면 /data/recruitment 파일을 읽어 메타 생성."""
    existing = db.query(models.Recruitment).count()
    if existing > 0:
        return

    for file_path in RECRUITMENT_DIR.glob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTS:
            continue

        raw_text = ""
        try:
            raw_text = load_document_text(file_path)
        except Exception:
            raw_text = ""

        title = file_path.stem
        summary = _summarize_text(raw_text, length=500)

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
            file_path=str(file_path),
        )
        db.add(rec)
    db.commit()


@router.get("/", response_model=List[schemas.RecruitmentSchema])
def list_recruitments(db: Session = Depends(get_db)) -> List[schemas.RecruitmentSchema]:
    _seed_from_files(db)
    items: List[models.Recruitment] = (
        db.query(models.Recruitment)
        .order_by(models.Recruitment.created_at.desc())
        .all()
    )
    # raw_text 및 배지 정보 계산
    for rec in items:
        try:
            raw_text = load_document_text(Path(rec.file_path))
        except Exception:
            raw_text = ""
        info = _extract_info(raw_text)
        rec.first_line = info["first_line"]
        rec.experience_badge = info["experience_badge"]
        rec.location_badge = info["location_badge"]
        rec.requirement_keywords = info["requirement_keywords"]
    return items


@router.get("/{recruitment_id}", response_model=schemas.RecruitmentSchema)
def get_recruitment(
    recruitment_id: int,
    db: Session = Depends(get_db),
) -> schemas.RecruitmentSchema:
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
    return rec
