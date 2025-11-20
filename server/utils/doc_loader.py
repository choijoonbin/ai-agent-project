# server/utils/doc_loader.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docx import Document
from PyPDF2 import PdfReader


# 지원할 확장자
SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".docx"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_documents(directory: Path) -> list[dict]:
    """
    지정된 디렉토리 아래의 지원 확장자 파일 목록을 반환.
    - id: 파일명 (예: sample.docx)
    - filename: 동일
    - ext: 확장자
    - size: 바이트
    - modified_at: ISO 문자열
    """
    ensure_dir(directory)
    items: list[dict] = []

    for p in directory.iterdir():
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            continue

        stat = p.stat()
        items.append(
            {
                "id": p.name,
                "filename": p.name,
                "display_name": p.stem,
                "ext": ext,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,  # 프론트에서 필요하면 포맷팅
            }
        )

    # 최근 수정 순으로 정렬 (내림차순)
    items.sort(key=lambda x: x["modified_at"], reverse=True)
    return items


def _load_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_md(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    texts: list[str] = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        texts.append(txt)
    return "\n\n".join(texts)


def _load_docx(path: Path) -> str:
    doc = Document(str(path))
    lines: list[str] = []
    for para in doc.paragraphs:
        if para.text:
            lines.append(para.text)
    return "\n".join(lines)


def load_document_text(path: Path) -> str:
    """
    파일 확장자에 따라 텍스트를 추출.
    지원 확장자: .txt, .md, .pdf, .docx
    """
    ext = path.suffix.lower()
    if ext == ".txt":
        return _load_txt(path)
    if ext == ".md":
        return _load_md(path)
    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    raise ValueError(f"Unsupported file extension: {ext}")
