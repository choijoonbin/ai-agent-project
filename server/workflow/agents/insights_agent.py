# server/workflow/agents/insights_agent.py

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from langchain_core.messages import SystemMessage, HumanMessage

from retrieval.vector_store import search_similar_documents
from utils.config import get_client, get_llm  # 이미 다른 곳에서 쓰고 있는 OpenAI client 헬퍼라 가정

logger = logging.getLogger(__name__)


class InsightsAgent:
    """
    인사이트 에이전트
    - 기본 LLM 기반 인사이트 생성
    - 옵션: 간단한 in-memory RAG 레이어를 통해 JD/이력서/QA/Evaluation 에서 관련 문맥을 먼저 추출
    """

    def __init__(
        self,
        use_rag: bool = True,
        use_mini: bool = True,
        embedding_model: str = "text-embedding-3-small",
        rag_chunk_size: int = 800,
        rag_chunk_overlap: int = 200,
        rag_top_k: int = 8,
    ) -> None:
        self.use_rag = use_rag
        self.use_mini = use_mini
        self.embedding_model = embedding_model
        self.rag_chunk_size = rag_chunk_size
        self.rag_chunk_overlap = rag_chunk_overlap
        self.rag_top_k = rag_top_k

        # OpenAI client (Responses + Embeddings 둘 다 사용)
        self.client = get_client()

    # ---------- RAG 유틸 ---------- #

    def _build_kb_context(self, state: Dict[str, Any]) -> str:
        """
        기존 벡터스토어(knowledge_base)를 활용해 온보딩/기여도/리스크 관련 문서를 검색.
        """
        job_title = state.get("job_title", "")
        candidate_name = state.get("candidate_name", "")

        queries = [
            f"{job_title} 온보딩 가이드",
            f"{job_title} 초기 90일 플랜",
            f"{job_title} 리스크 평가",
            f"{job_title} 성장/코칭 포인트",
        ]

        snippets: List[str] = []
        for q in queries:
            try:
                docs = search_similar_documents(q, k=max(1, self.rag_top_k // 2))
            except Exception as e:
                logger.debug(f"[InsightsAgent] KB 검색 실패 ({q}): {e}")
                continue
            for i, doc in enumerate(docs):
                source = doc.metadata.get("source", "knowledge_base")
                snippets.append(f"[KB-{candidate_name or 'candidate'}-{i+1}] {source}\n{doc.page_content}")

        return "\n\n".join(snippets)

    def _split_text(self, text: str) -> List[str]:
        """
        아주 단순한 chunking: rag_chunk_size 기준으로 문자를 잘라서 겹치게 붙임.
        """
        chunks: List[str] = []
        if not text:
            return chunks

        step = self.rag_chunk_size - self.rag_chunk_overlap
        for i in range(0, len(text), step):
            chunk = text[i : i + self.rag_chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        return chunks

    def _embed_texts(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        OpenAI Embeddings API 호출.
        - 실패하면 None 반환 (fallback 용)
        """
        if not texts:
            return None
        try:
            resp = self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )
            # openai==1.x 응답 형식: resp.data[i].embedding
            vectors = [item.embedding for item in resp.data]
            return np.array(vectors, dtype=np.float32)
        except Exception as e:
            logger.warning(f"[InsightsAgent] Embeddings 생성 실패: {e}")
            return None

    def _build_rag_context(self, state: Dict[str, Any]) -> str:
        """
        JD / 이력서 / QA / 평가 요약을 기반으로
        in-memory vector store를 만들고,
        '온보딩/기여도/리스크 분석'에 유용한 top-K 정보를 뽑아 문자열로 만든다.
        """
        try:
            source_snippets: List[str] = []

            jd_text = state.get("jd_text") or state.get("jd") or ""
            resume_text = state.get("resume_text") or state.get("resume") or ""

            if jd_text:
                source_snippets.append(f"[JD]\n{jd_text}")
            if resume_text:
                source_snippets.append(f"[RESUME]\n{resume_text}")

            # QA History
            qa_history = state.get("qa_history") or []
            if qa_history:
                qa_snippets: List[str] = []
                for turn in qa_history:
                    q = turn.get("question", "")
                    a = turn.get("answer", "")
                    if q or a:
                        qa_snippets.append(f"Q: {q}\nA: {a}")
                if qa_snippets:
                    source_snippets.append("[INTERVIEW_QA]\n" + "\n\n".join(qa_snippets))

            # Evaluation summary
            evaluation = state.get("evaluation") or {}
            summary = evaluation.get("summary") or ""
            if summary:
                source_snippets.append("[EVALUATION_SUMMARY]\n" + summary)

            # chunking
            chunks: List[str] = []
            for snippet in source_snippets:
                chunks.extend(self._split_text(snippet))

            if not chunks:
                return ""

            # embedding
            vecs = self._embed_texts(chunks)
            if vecs is None or vecs.size == 0:
                return ""

            # query embedding
            query_text = (
                "이 후보자의 채용 이후 온보딩(Soft-landing), "
                "단기/장기 기여도, 리스크와 성장 가능성을 분석하는 데 도움이 되는 정보를 찾아라."
            )
            q_vecs = self._embed_texts([query_text])
            if q_vecs is None or q_vecs.size == 0:
                return ""

            q_vec = q_vecs[0]  # (d,)
            # cosine similarity
            dot = np.dot(vecs, q_vec)
            norms = np.linalg.norm(vecs, axis=1) * np.linalg.norm(q_vec)
            sims = dot / (norms + 1e-8)

            # Top-K 인덱스
            top_k = min(self.rag_top_k, len(chunks))
            top_idx = np.argsort(-sims)[:top_k]

            selected_chunks = [chunks[i] for i in top_idx]
            rag_context = "\n\n---\n\n".join(selected_chunks)
            return rag_context
        except Exception as e:
            logger.warning(f"[InsightsAgent] RAG context 생성 중 예외 발생: {e}")
            return ""

    # ---------- Prompt ---------- #

    def _build_prompt(
        self,
        state: Dict[str, Any],
        rag_context: str = "",
    ) -> str:
        """
        RAG 컨텍스트가 있으면 상단에 붙이고,
        기존 state 기반 요약 정보와 함께 인사이트 생성을 요청하는 prompt 생성.
        """

        jd_text = (state.get("jd_text") or state.get("jd") or "")[:4000]
        resume_text = (state.get("resume_text") or state.get("resume") or "")[:4000]

        evaluation = state.get("evaluation") or {}
        summary = evaluation.get("summary") or ""
        scores = evaluation.get("scores") or {}
        recommendation = evaluation.get("recommendation") or ""

        qa_history = state.get("qa_history") or []

        lines: List[str] = []

        if rag_context:
            lines.append(
                "다음은 JD/이력서/인터뷰 내역/평가 요약을 기반으로 RAG 검색으로 추출한 관련 정보입니다."
            )
            lines.append("이 정보를 우선적으로 참고해서 인사이트를 만들어주세요.")
            lines.append("")
            lines.append("<<RAG_CONTEXT_START>>")
            lines.append(rag_context)
            lines.append("<<RAG_CONTEXT_END>>")
            lines.append("")

        lines.append("아래는 후보자와 관련된 원본 정보입니다.")
        lines.append("가능하면 중복 설명은 줄이고, 위 RAG 컨텍스트를 우선 사용하세요.")
        lines.append("")
        if jd_text:
            lines.append("=== JD (채용 공고) 요약 ===")
            lines.append(jd_text)
            lines.append("")
        if resume_text:
            lines.append("=== 이력서 요약 ===")
            lines.append(resume_text)
            lines.append("")
        if qa_history:
            lines.append("=== 인터뷰 Q&A 일부 ===")
            for i, turn in enumerate(qa_history[:10], start=1):
                q = turn.get("question", "")
                a = turn.get("answer", "")
                lines.append(f"[Q{i}] {q}")
                if a:
                    lines.append(f"[A{i}] {a}")
                lines.append("")
        if summary or scores or recommendation:
            lines.append("=== 평가 요약 ===")
            if summary:
                lines.append(f"- 요약: {summary}")
            if recommendation:
                lines.append(f"- 최종 추천: {recommendation}")
            if scores:
                lines.append(f"- 역량별 점수: {json.dumps(scores, ensure_ascii=False)}")
            lines.append("")

        lines.append(
            """
당신은 채용 담당자를 돕는 시니어 HR/조직 컨설턴트입니다.
위의 정보를 기반으로, 아래 JSON 형식으로만 응답하세요:

{
  "soft_landing_plan": {
    "summary": "...",
    "days_30": ["...", "..."],
    "days_60": ["...", "..."],
    "days_90": ["...", "..."]
  },
  "contribution_analysis": {
    "short_term": {
      "score": 1~5,
      "summary": "..."
    },
    "long_term": {
      "score": 1~5,
      "summary": "..."
    }
  },
  "risk_points": [
    {
      "label": "...",
      "severity": "low|medium|high",
      "description": "..."
    }
  ],
  "raw_text": "사람이 읽기 좋은 자연어 전체 요약"
}

- JSON 이외의 텍스트는 절대 포함하지 마세요.
- score 값은 1~5 정수로만 넣으세요.
"""
        )

        return "\n".join(lines)

    def _call_responses_api(self, prompt: str, model: str) -> str:
        """OpenAI Responses API 호출(Fallback)."""
        resp = self.client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "당신은 채용 담당자를 돕는 HR/조직 인사이트 전문가입니다.",
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                },
            ],
            temperature=0.25,
        )
        # openai==1.x Responses 편의 프로퍼티 (있으면 사용)
        if hasattr(resp, "output_text"):
            return resp.output_text

        msg = resp.output[0]
        block = msg.content[0]
        if hasattr(block, "text") and hasattr(block.text, "value"):
            return block.text.value
        return str(block)

    # ---------- 실행 ---------- #

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        RAG → LLM 인사이트 생성
        - RAG 단계가 실패하거나 빈 결과면: 기존 LLM 로직(비-RAG) 과 동일한 prompt로 실행
        """
        # 1) RAG 컨텍스트 (KB + state 기반)
        rag_context_parts: List[str] = []
        if self.use_rag:
            kb_ctx = self._build_kb_context(state)
            state_ctx = self._build_rag_context(state)
            if kb_ctx:
                rag_context_parts.append(kb_ctx)
            if state_ctx:
                rag_context_parts.append(state_ctx)

        rag_context = "\n\n====\n\n".join(rag_context_parts)

        # 2) Prompt 생성
        prompt = self._build_prompt(state, rag_context=rag_context)

        # 3) LLM 호출: RAG 컨텍스트가 있으면 LangChain LLM, 없으면 Responses API로 fallback
        raw = ""
        if rag_context:
            try:
                llm = get_llm(use_mini=self.use_mini, streaming=False)
                resp = llm.invoke(
                    [
                        SystemMessage(content="당신은 채용 담당자를 돕는 HR/조직 인사이트 전문가입니다."),
                        HumanMessage(content=prompt),
                    ]
                )
                raw = getattr(resp, "content", "") or ""
            except Exception as e:
                logger.warning(f"[InsightsAgent] LangChain LLM 호출 실패, Responses API로 fallback: {e}")

        model = "gpt-4.1-mini" if self.use_mini else "gpt-4.1"

        if not raw:
            try:
                raw = self._call_responses_api(prompt, model=model)
            except Exception as e:
                logger.error(f"[InsightsAgent] Responses API 실패: {e}")
                return {
                    "soft_landing_plan": {},
                    "contribution_analysis": {},
                    "risk_points": [],
                    "raw_text": f"인사이트 생성 중 오류 발생: {e}",
                }

        # 4) JSON 파싱
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("[InsightsAgent] LLM 응답이 JSON 파싱에 실패, raw_text 로 감쌈.")
            data = {
                "soft_landing_plan": {},
                "contribution_analysis": {},
                "risk_points": [],
                "raw_text": raw,
            }

        # raw_text 누락 시 보정
        if "raw_text" not in data:
            data["raw_text"] = raw

        return data
