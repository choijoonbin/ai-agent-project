# Langfuse 설정 및 확인 가이드

## 현재 설정 상태

✅ SSL 검증 비활성화 완료
✅ CallbackHandler 생성 로직 수정 완료
✅ LangGraph 콜백 전달 설정 완료

## Langfuse 대시보드에서 데이터 확인 방법

### 1. Langfuse 대시보드 접속
- URL: `https://cloud.langfuse.com` (또는 설정한 LANGFUSE_HOST)
- 로그인 후 프로젝트 선택

### 2. 데이터 확인 위치
- **Traces 메뉴**: 모든 추적 데이터 확인
- **Sessions 메뉴**: 세션별로 그룹화된 데이터 확인
- **Logs 메뉴**: 상세 로그 확인

### 3. 검색 방법
- **Session ID로 검색**: 서버 로그에 출력된 Session ID로 검색
- **태그로 검색**: `interview_workflow` 태그로 검색
- **시간 범위**: 최근 실행한 시간대를 선택

### 4. 확인해야 할 데이터
- **JD Analyzer Agent**: JD 분석 LLM 호출
- **Resume Analyzer Agent**: 이력서 분석 LLM 호출  
- **Interviewer Agent**: 면접 질문 생성 LLM 호출
- **Judge Agent**: 평가 리포트 생성 LLM 호출

## 문제 해결

### 데이터가 보이지 않는 경우

1. **환경 변수 확인**
   ```bash
   # server/.env 파일 확인
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```

2. **서버 로그 확인**
   - "Langfuse CallbackHandler 생성 완료" 메시지 확인
   - "LangGraph 실행 완료. Langfuse Session ID: ..." 메시지 확인

3. **테스트 실행**
   ```bash
   cd server
   python3 test_langfuse.py
   ```
   - 테스트가 성공하면 Langfuse 설정은 정상입니다.

4. **Langfuse 대시보드 확인**
   - 대시보드에서 "test-session-123" 세션 검색
   - 데이터가 보이면 정상 동작 중입니다.

### 추가 디버깅

서버 로그에서 다음을 확인하세요:
- CallbackHandler 생성 로그
- LangGraph 실행 완료 로그
- Session ID 값

이 정보들을 Langfuse 대시보드에서 검색하면 데이터를 찾을 수 있습니다.

