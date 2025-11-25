# server/routers/auth.py

from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db import models, schemas

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    role_type: str  # "applicant" | "manager"
    name: str
    birth: str | None = None  # 관리자 로그인은 생년월일 없이 이름만


class LoginResponse(BaseModel):
    status: str
    member_id: int
    role: str
    name: str
    birth: str


class SignupRequest(BaseModel):
    name: str
    birth: str


class SignupResponse(BaseModel):
    status: str
    member_id: int
    name: str
    birth: str
    role: str


def _ensure_admin_seed(db: Session) -> models.Member:
    """요구사항에 따라 관리자 계정을 보장."""
    admin = (
        db.query(models.Member)
        .filter(models.Member.name == "관리자", models.Member.role == "ADMIN")
        .first()
    )
    if admin:
        return admin
    admin = models.Member(
        name="관리자",
        birth="1900-01-01",
        role="ADMIN",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    if request.role_type == "manager":
        admin = _ensure_admin_seed(db)
        if request.name != admin.name:
            raise HTTPException(status_code=401, detail="관리자 이름이 올바르지 않습니다.")
        return LoginResponse(
            status="success",
            member_id=admin.id,
            role=admin.role,
            name=admin.name,
            birth=admin.birth,
        )

    if not request.birth:
        raise HTTPException(status_code=400, detail="생년월일이 필요합니다.")

    member = (
        db.query(models.Member)
        .filter(
            models.Member.name == request.name,
            models.Member.birth == request.birth,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=401, detail="이름/생년월일이 일치하지 않습니다.")

    return LoginResponse(
        status="success",
        member_id=member.id,
        role=member.role,
        name=member.name,
        birth=member.birth,
    )


@router.post("/signup", response_model=SignupResponse)
def signup(request: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    exists = (
        db.query(models.Member)
        .filter(
            models.Member.name == request.name,
            models.Member.birth == request.birth,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="이미 가입된 사용자입니다.")

    member = models.Member(
        name=request.name,
        birth=request.birth,
        role="NORMAL",
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    return SignupResponse(
        status="success",
        member_id=member.id,
        name=member.name,
        birth=member.birth,
        role=member.role,
    )


@router.get("/members/normal", response_model=List[schemas.MemberSchema])
def list_normal_members(db: Session = Depends(get_db)) -> List[schemas.MemberSchema]:
    """NORMAL 역할의 멤버 목록을 반환합니다."""
    members = (
        db.query(models.Member)
        .filter(models.Member.role == "NORMAL")
        .order_by(models.Member.name)
        .all()
    )
    return [
        schemas.MemberSchema(
            id=m.id,
            name=m.name,
            birth=m.birth,
            role=m.role,
            created_at=m.created_at,
        )
        for m in members
    ]
