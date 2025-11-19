# server/retrieval/loader.py

from pathlib import Path
from typing import List

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 프로젝트 기준으로 knowledge base 경로 지정
# server/
#   retrieval/
#   data/
#     knowledge_base/   ← 여기에 .txt / .md 파일을 넣어두면 됩니다.
BASE_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = BASE_DIR / "data" / "knowledge_base"


def load_raw_documents() -> List[Document]:
    """
    knowledge_base 디렉터리에서 원본 문서를 읽어옵니다.
    현재는 .txt / .md 파일만 대상으로 합니다.
    """
    if not KNOWLEDGE_BASE_DIR.exists():
        # 디렉터리가 없으면 빈 리스트 반환
        return []

    docs: List[Document] = []

    # 필요한 패턴을 추가해서 확장 가능
    patterns = ["**/*.txt", "**/*.md"]

    for pattern in patterns:
        loader = DirectoryLoader(
            str(KNOWLEDGE_BASE_DIR),
            glob=pattern,
            loader_cls=TextLoader,
            show_progress=True,
            use_multithreading=True,
        )
        docs.extend(loader.load())

    return docs


def split_documents(docs: List[Document]) -> List[Document]:
    """
    긴 문서를 잘게 쪼개어 RAG에 적합한 chunk 단위로 만듭니다.
    """
    if not docs:
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,      # 한 청크 최대 길이
        chunk_overlap=200,   # 청크 간 겹치는 길이
        add_start_index=True,
    )

    return text_splitter.split_documents(docs)


def load_knowledge_documents() -> List[Document]:
    """
    RAG용으로 사용할 최종 Document 리스트를 반환합니다.
    1) 파일로부터 로드 → 2) 청크 분할까지 포함.
    """
    raw_docs = load_raw_documents()
    if not raw_docs:
        return []

    chunked_docs = split_documents(raw_docs)
    return chunked_docs
