# server/retrieval/vector_store.py

from pathlib import Path
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from retrieval.loader import load_knowledge_documents
from utils.config import get_embeddings

# server/
#   data/
#     vector_store/
#       faiss_index/
BASE_DIR = Path(__file__).resolve().parents[1]
VECTOR_STORE_DIR = BASE_DIR / "data" / "vector_store"
VECTOR_STORE_PATH = VECTOR_STORE_DIR / "faiss_index"

# 프로세스 내에서 재사용할 캐시
_vector_store: Optional[FAISS] = None


def build_vector_store(force_rebuild: bool = False) -> FAISS:
    """
    knowledge_base 문서들을 읽어와 새로 FAISS 벡터스토어를 생성합니다.
    - force_rebuild=True: 기존 캐시/파일과 상관없이 다시 빌드
    """
    global _vector_store

    if _vector_store is not None and not force_rebuild:
        return _vector_store

    docs = load_knowledge_documents()
    if not docs:
        raise RuntimeError(
            "지식 베이스 문서를 찾을 수 없습니다. "
            "server/data/knowledge_base/ 아래에 .txt 또는 .md 파일을 추가해주세요."
        )

    embeddings = get_embeddings()
    vs = FAISS.from_documents(docs, embeddings)

    # 로컬 디렉터리에 저장 (나중에 재사용)
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    vs.save_local(str(VECTOR_STORE_PATH))

    _vector_store = vs
    return vs


def load_vector_store() -> Optional[FAISS]:
    """
    디스크에 저장된 FAISS 인덱스를 로드합니다.
    - 처음 실행이거나 파일이 없으면 None 반환.
    """
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    if VECTOR_STORE_PATH.exists():
        embeddings = get_embeddings()
        _vector_store = FAISS.load_local(
            str(VECTOR_STORE_PATH),
            embeddings,
            allow_dangerous_deserialization=True,
        )
        return _vector_store

    return None


def get_vector_store(auto_build: bool = True) -> FAISS:
    """
    벡터스토어 핸들을 가져옵니다.
    - 이미 로드되어 있으면 캐시 사용
    - 디스크에만 있으면 로드
    - 둘 다 없으면 auto_build=True 인 경우 새로 빌드
    """
    vs = load_vector_store()
    if vs is not None:
        return vs

    if auto_build:
        return build_vector_store(force_rebuild=True)

    raise RuntimeError("Vector store가 초기화되어 있지 않습니다.")


def search_similar_documents(query: str, k: int = 5) -> List[Document]:
    """
    주어진 쿼리로 FAISS 벡터스토어에서 유사도가 높은 문서를 검색합니다.
    """
    vs = get_vector_store(auto_build=True)
    results = vs.similarity_search(query, k=k)
    return results
