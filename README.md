# AI Interview Agent

AI 기반 자동화 면접 시스템으로, 채용 공고(JD)와 지원자 이력서를 분석하여 맞춤형 면접 질문을 생성하고, 답변을 평가하는 멀티 에이전트 워크플로우를 제공합니다.

## 📋 목차

- [프로젝트 개요](#프로젝트-개요)
- [주요 기능](#주요-기능)
- [프로젝트 구조](#프로젝트-구조)
- [기술 스택](#기술-스택)
- [동작 원리](#동작-원리)
- [설치 및 실행](#설치-및-실행)
- [환경 변수 설정](#환경-변수-설정)
- [API 엔드포인트](#api-엔드포인트)
- [Langfuse 통합](#langfuse-통합)

## 🎯 프로젝트 개요

이 프로젝트는 **LangGraph**를 활용한 멀티 에이전트 시스템으로, 다음과 같은 면접 프로세스를 자동화합니다:

1. **JD 분석**: 채용 공고에서 요구 역량, 기술 스택, 경험 요구사항 추출
2. **이력서 분석**: 지원자의 경력, 기술, 프로젝트 경험 분석 및 JD 매칭
3. **면접 질문 생성**: JD와 이력서를 기반으로 맞춤형 면접 질문 자동 생성
4. **평가 리포트 생성**: 질문-답변을 바탕으로 종합 평가 및 추천 여부 결정

## ✨ 주요 기능

### 1. 멀티 에이전트 워크플로우
- **JD Analyzer Agent**: 채용 공고 분석 및 요구사항 추출
- **Resume Analyzer Agent**: 이력서 분석 및 JD 매칭 평가
- **Interviewer Agent**: 맞춤형 면접 질문 생성
- **Judge Agent**: 최종 평가 리포트 및 추천 생성

### 2. RAG (Retrieval Augmented Generation)
- FAISS 벡터 스토어를 활용한 지식 베이스 검색
- 포지션별(백엔드, 프론트엔드, DevOps, ML/AI 등) 면접 가이드 및 평가 기준 제공
- 각 에이전트가 RAG 컨텍스트를 활용하여 더 정확한 분석 수행

### 3. LLM 관찰성 (Observability)
- **Langfuse** 통합을 통한 모든 LLM 호출 추적
- 세션별, 에이전트별 상세 로그 및 성능 모니터링
- 대시보드에서 실시간 추적 및 분석 가능

### 4. 면접 이력 관리
- SQLite 데이터베이스를 통한 면접 결과 저장
- 이력 조회 및 재평가 기능 제공
- Streamlit UI를 통한 직관적인 인터페이스

## 📁 프로젝트 구조

```
ai-interview-agent/
├── app/                          # Streamlit 프론트엔드
│   ├── main.py                  # 메인 Streamlit 앱
│   ├── components/              # UI 컴포넌트
│   │   ├── candidate_form.py   # 지원자 정보 입력 폼
│   │   ├── history_panel.py    # 면접 이력 패널
│   │   ├── interview_chat.py   # 면접 채팅 인터페이스
│   │   └── sidebar.py          # 사이드바 설정
│   └── utils/
│       └── state_manager.py     # 세션 상태 관리
│
├── server/                       # FastAPI 백엔드
│   ├── main.py                  # FastAPI 앱 진입점
│   │
│   ├── workflow/                # LangGraph 워크플로우
│   │   ├── graph.py            # 워크플로우 그래프 정의
│   │   ├── state.py            # 공유 상태(State) 정의
│   │   └── agents/             # 에이전트 구현
│   │       ├── base_agent.py  # 베이스 에이전트 클래스
│   │       ├── jd_agent.py    # JD 분석 에이전트
│   │       ├── resume_agent.py # 이력서 분석 에이전트
│   │       ├── interview_agent.py # 면접 질문 생성 에이전트
│   │       └── judge_agent.py  # 평가 에이전트
│   │
│   ├── retrieval/               # RAG 관련 모듈
│   │   ├── loader.py           # 지식 베이스 문서 로더
│   │   ├── vector_store.py     # FAISS 벡터 스토어 관리
│   │   └── tools.py            # RAG 유틸리티
│   │
│   ├── routers/                 # FastAPI 라우터
│   │   ├── workflow.py         # 워크플로우 실행 API
│   │   └── history.py          # 면접 이력 조회 API
│   │
│   ├── db/                      # 데이터베이스
│   │   ├── database.py         # DB 연결 설정
│   │   ├── models.py           # SQLAlchemy 모델
│   │   └── schemas.py          # Pydantic 스키마
│   │
│   ├── utils/                   # 유틸리티
│   │   └── config.py           # 설정 관리 (LLM, Langfuse 등)
│   │
│   └── data/                    # 데이터 파일
│       ├── knowledge_base/      # RAG용 지식 베이스 문서
│       │   ├── backend/        # 백엔드 포지션 관련 문서
│       │   ├── frontend/       # 프론트엔드 포지션 관련 문서
│       │   ├── devops/         # DevOps 포지션 관련 문서
│       │   └── ...            # 기타 포지션별 문서
│       └── vector_store/        # FAISS 인덱스 저장 경로
│
├── docker/                      # Docker 설정
│   ├── Dockerfile.api          # 백엔드 Dockerfile
│   ├── Dockerfile.app          # 프론트엔드 Dockerfile
│   └── docker-compose.yml      # Docker Compose 설정
│
├── requirements.txt            # Python 패키지 의존성
├── README.md                   # 프로젝트 문서
└── LANGFUSE_SETUP.md          # Langfuse 설정 가이드
```

## 🛠 기술 스택

### 백엔드
- **FastAPI** (0.104.0+): 고성능 비동기 웹 프레임워크
- **LangChain** (0.3.0+): LLM 애플리케이션 개발 프레임워크
- **LangGraph** (0.2.0+): 멀티 에이전트 워크플로우 오케스트레이션
- **Langfuse** (2.0.0+): LLM 관찰성 및 추적 플랫폼
- **FAISS** (1.7.4+): 벡터 유사도 검색 라이브러리
- **SQLAlchemy** (2.0.0+): ORM 및 데이터베이스 관리
- **Pydantic** (2.0.0+): 데이터 검증 및 설정 관리

### 프론트엔드
- **Streamlit** (최신): 빠른 웹 UI 개발 프레임워크

### LLM 및 임베딩
- **Azure OpenAI**: GPT 모델 (ChatGPT-4, GPT-3.5-turbo 등)
- **Azure OpenAI Embeddings**: 텍스트 임베딩 생성

### 데이터베이스
- **SQLite**: 경량 관계형 데이터베이스 (면접 이력 저장)

## 🔄 동작 원리

### 1. 워크플로우 흐름

```
[시작]
    ↓
[JD Analyzer Agent]
    ├─ JD 텍스트 분석
    ├─ RAG로 포지션별 가이드 검색
    └─ 요구 역량/기술/경험 추출
    ↓
[Resume Analyzer Agent]
    ├─ 이력서 텍스트 분석
    ├─ RAG로 평가 기준 검색
    └─ 핵심 기술 스택 및 경력 요약 추출
    ↓
[Interviewer Agent]
    ├─ JD 분석 결과 + 이력서 분석 결과 결합
    ├─ RAG로 면접 질문 예시 검색
    └─ 맞춤형 면접 질문 리스트 생성
    ↓
[Judge Agent]
    ├─ 전체 면접 데이터 수집
    ├─ RAG로 평가 기준 검색
    └─ 최종 평가 리포트 생성 (강점/약점/점수/추천)
    ↓
[종료]
```

### 2. 상태 관리 (State Management)

**LangGraph**는 `InterviewState`라는 공유 상태 객체를 통해 모든 에이전트 간 데이터를 공유합니다:

```python
class InterviewState(TypedDict):
    # 기본 정보
    job_title: str
    candidate_name: str
    jd_text: str
    resume_text: str
    
    # 분석 결과
    jd_summary: str
    jd_requirements: List[str]
    candidate_summary: str
    candidate_skills: List[str]
    
    # 면접 진행 상태
    qa_history: List[QATurn]
    total_questions: int
    status: InterviewStatus
    
    # RAG 컨텍스트
    rag_contexts: Dict[str, str]
    rag_docs: Dict[str, List[Any]]
    
    # 최종 평가 결과
    evaluation: Optional[EvaluationResult]
```

각 에이전트는 이 상태를 읽고 업데이트하면서 순차적으로 작업을 수행합니다.

### 3. RAG (Retrieval Augmented Generation)

각 에이전트는 필요에 따라 FAISS 벡터 스토어에서 유사한 문서를 검색하여 컨텍스트로 활용합니다:

1. **문서 로딩**: `server/data/knowledge_base/` 디렉토리에서 `.txt`, `.md` 파일 로드
2. **청크 분할**: `RecursiveCharacterTextSplitter`로 문서를 800자 단위로 분할
3. **임베딩 생성**: Azure OpenAI Embeddings로 벡터화
4. **FAISS 인덱싱**: 벡터를 FAISS 인덱스로 저장
5. **유사도 검색**: 쿼리와 유사한 상위 k개 문서 검색

### 4. Langfuse 통합

모든 LLM 호출은 **Langfuse CallbackHandler**를 통해 자동으로 추적됩니다:

- 각 에이전트의 LLM 호출이 세션별로 그룹화되어 추적
- LangGraph의 `thread_id`를 통해 워크플로우 전체를 하나의 세션으로 관리
- Langfuse 대시보드에서 실시간으로 추적 및 분석 가능

## 🚀 설치 및 실행

### 1. 저장소 클론

```bash
git clone <repository-url>
cd ai-interview-agent
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`server/.env` 파일을 생성하고 필요한 환경 변수를 설정합니다 (자세한 내용은 [환경 변수 설정](#환경-변수-설정) 참조).

### 4. 백엔드 서버 실행

```bash
cd server
uvicorn main:app --reload --port 9898
```

백엔드 API는 `http://localhost:9898`에서 실행됩니다.

### 5. 프론트엔드 실행

새 터미널에서:

```bash
cd app
streamlit run main.py
```

Streamlit 앱은 기본적으로 `http://localhost:8501`에서 실행됩니다.

## ⚙️ 환경 변수 설정

### `server/.env` 파일 예시

```env
# 프로젝트 설정
PROJECT_NAME=AI Interview Agent
DB_PATH=interview_history.db

# Azure OpenAI 설정
AZURE_OPENAI_API_KEY=your-azure-openai-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-ada-002

# Langfuse 설정 (선택사항)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# CORS 설정
BACKEND_CORS_ORIGINS=["http://localhost:8501","http://localhost:3000"]
```

### `app/.env` 파일 예시

```env
API_BASE_URL=http://localhost:9898/api/v1
```

## 📡 API 엔드포인트

### 1. 면접 워크플로우 실행

**POST** `/api/v1/workflow/interview/run`

면접 워크플로우를 실행하고 결과를 반환합니다.

**Request Body:**
```json
{
  "job_title": "백엔드 개발자",
  "candidate_name": "홍길동",
  "jd_text": "채용 공고 내용...",
  "resume_text": "이력서 내용...",
  "total_questions": 5,
  "enable_rag": true,
  "use_mini": false,
  "save_history": true
}
```

**Response:**
```json
{
  "status": "DONE",
  "state": {
    "job_title": "백엔드 개발자",
    "jd_summary": "...",
    "qa_history": [...],
    "evaluation": {...}
  },
  "interview_id": 1
}
```

### 2. 면접 이력 조회

**GET** `/api/v1/interviews/?limit=20`

면접 이력 목록을 조회합니다.

### 3. 면접 상세 조회

**GET** `/api/v1/interviews/{interview_id}`

특정 면접의 상세 정보를 조회합니다.

### 4. 재평가 실행

**POST** `/api/v1/workflow/interview/rejudge`

수정된 질문-답변을 기반으로 Judge Agent만 재실행합니다.

**Request Body:**
```json
{
  "interview_id": 1,
  "qa_history": [
    {
      "question": "질문 내용",
      "answer": "답변 내용",
      "category": "기술"
    }
  ],
  "enable_rag": true,
  "use_mini": false
}
```

## 🔍 Langfuse 통합

Langfuse를 통한 LLM 추적 및 관찰성을 활용하려면:

1. **Langfuse 계정 생성**: https://cloud.langfuse.com 에서 계정 생성
2. **API 키 발급**: Public Key와 Secret Key 발급
3. **환경 변수 설정**: `server/.env`에 Langfuse 설정 추가
4. **대시보드 확인**: Langfuse 대시보드에서 세션별 추적 데이터 확인

자세한 설정 방법은 [LANGFUSE_SETUP.md](./LANGFUSE_SETUP.md)를 참조하세요.

### Langfuse에서 확인 가능한 정보

- **Traces**: 모든 LLM 호출의 상세 로그
- **Sessions**: 세션별로 그룹화된 워크플로우 실행 기록
- **Latency**: 각 에이전트의 실행 시간
- **Token Usage**: LLM 호출별 토큰 사용량
- **Cost**: 비용 추적

## 📝 사용 예시

### Streamlit UI 사용

1. 브라우저에서 `http://localhost:8501` 접속
2. 채용 공고(JD)와 지원자 이력서 입력
3. "AI 면접 에이전트 실행" 버튼 클릭
4. 생성된 면접 질문 확인 및 답변 입력
5. 최종 평가 결과 확인

### API 직접 호출

```python
import requests

url = "http://localhost:9898/api/v1/workflow/interview/run"
payload = {
    "job_title": "백엔드 개발자",
    "candidate_name": "홍길동",
    "jd_text": "채용 공고 내용...",
    "resume_text": "이력서 내용...",
    "total_questions": 5,
    "enable_rag": True,
    "use_mini": False,
    "save_history": True
}

response = requests.post(url, json=payload)
result = response.json()
print(result["state"]["evaluation"])
```

## 🧪 테스트

### Langfuse 연결 테스트

```bash
cd server
python3 test_langfuse.py
```

## 📚 추가 문서

- [LANGFUSE_SETUP.md](./LANGFUSE_SETUP.md): Langfuse 설정 및 사용 가이드

## 🤝 기여

이슈 리포트 및 풀 리퀘스트를 환영합니다.

## 📄 라이선스

[라이선스 정보를 여기에 추가하세요]

---

**개발자**: AI Interview Agent Team  
**버전**: 0.1.0
