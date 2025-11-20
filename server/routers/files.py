# server/routers/files.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from docx import Document
from pypdf import PdfReader

router = APIRouter(
    prefix="/api/v1/files",
    tags=["files"],
)

# --- 디렉터리 설정 ---
BASE_DIR = Path(__file__).resolve().parents[1]
JD_DIR = BASE_DIR / "data" / "recruitment"
RESUME_DIR = BASE_DIR / "data" / "resume"

ALLOWED_EXTS = {".docx", ".pdf", ".md", ".txt"}

JD_DIR.mkdir(parents=True, exist_ok=True)
RESUME_DIR.mkdir(parents=True, exist_ok=True)


class FileSummary(BaseModel):
    id: str          # 프론트에서 사용할 식별자 (여기서는 파일명 사용)
    filename: str
    display_name: str
    ext: str
    size: int
    modified_at: datetime


class FileContent(BaseModel):
    id: str
    filename: str
    content: str


def _list_files_in(dir_path: Path) -> List[FileSummary]:
    items: List[FileSummary] = []
    for p in sorted(dir_path.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in ALLOWED_EXTS:
            continue

        stat = p.stat()
        items.append(
            FileSummary(
                id=p.name,
                filename=p.name,
                display_name=p.stem,
                ext=ext,
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    return items


def _read_file_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    elif ext == ".pdf":
        texts = []
        with path.open("rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                texts.append(page.extract_text() or "")
        return "\n".join(texts)
    elif ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 확장자입니다: {ext}")


# ---------- JD 리스트 / 내용 ---------- #

@router.get("/jd", response_model=List[FileSummary])
def list_jd_files() -> List[FileSummary]:
    return _list_files_in(JD_DIR)


@router.get("/jd/{file_id}", response_model=FileContent)
def get_jd_file(file_id: str) -> FileContent:
    path = (JD_DIR / file_id).resolve()
    if not str(path).startswith(str(JD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="잘못된 파일 경로입니다.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if path.suffix.lower() not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다.")

    content = _read_file_text(path)
    return FileContent(id=file_id, filename=path.name, content=content)


@router.post("/jd/upload", response_model=FileSummary)
async def upload_jd_file(file: UploadFile = File(...)) -> FileSummary:
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다.")

    filename = Path(file.filename).name
    dest = JD_DIR / filename

    data = await file.read()
    dest.write_bytes(data)

    # 저장 후 메타 정보 반환
    stat = dest.stat()
    return FileSummary(
        id=dest.name,
        filename=dest.name,
        display_name=dest.stem,
        ext=ext,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime),
    )


# ---------- 이력서 리스트 / 내용 ---------- #

@router.get("/resume", response_model=List[FileSummary])
def list_resume_files() -> List[FileSummary]:
    return _list_files_in(RESUME_DIR)


@router.get("/resume/{file_id}", response_model=FileContent)
def get_resume_file(file_id: str) -> FileContent:
    path = (RESUME_DIR / file_id).resolve()
    if not str(path).startswith(str(RESUME_DIR.resolve())):
        raise HTTPException(status_code=400, detail="잘못된 파일 경로입니다.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if path.suffix.lower() not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다.")

    content = _read_file_text(path)
    return FileContent(id=file_id, filename=path.name, content=content)


@router.post("/resume/upload", response_model=FileSummary)
async def upload_resume_file(file: UploadFile = File(...)) -> FileSummary:
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다.")

    filename = Path(file.filename).name
    dest = RESUME_DIR / filename

    data = await file.read()
    dest.write_bytes(data)

    stat = dest.stat()
    return FileSummary(
        id=dest.name,
        filename=dest.name,
        display_name=dest.stem,
        ext=ext,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime),
    )
